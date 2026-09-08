"""
Sesión de una llamada con Gemini Live: PizzeriaCallSession reenvía audio en
ambas direcciones y despacha cada tool_call a ToolRouter. La misma clase
sirve tanto para la CLI local (run(), micro/altavoz) como para el servidor
Twilio (server.py crea una instancia por llamada entrante) - run_with_reconnect
es el punto de entrada compartido por los dos.

Dos mecanismos de robustez viven aquí, y merece la pena tenerlos claros:

- Watchdog de silencio (_idle_watchdog): una tarea de fondo que vigila cuánto
  lleva el cliente sin decir nada. Si pasa demasiado tiempo, empuja a Gemini a
  reaccionar (o cuelga como último recurso) - ver su docstring para los dos
  ritmos distintos que usa (llamada en curso vs. ya resuelta).
- Nudges (fragmentos de texto que se mandan a mitad de llamada, vía
  session.send_realtime_input): la forma de "avisar" a Gemini de algo sin
  esperar a que el cliente hable. Son la única herramienta disponible para
  esto, pero no una orden que el modelo cumpla siempre al pie de la letra -
  varios comentarios en este fichero documentan casos reales donde Gemini no
  siguió un nudge como se esperaba. Se usan solo donde no hay alternativa
  mejor (idle_watchdog, y empujar a gestionar_queja tras avisar_espera_
  incidencia - ver _handle_tool_call/_receive_and_play), nunca como sustituto
  de una validación real cuando esta es posible (ver agents/tools.py).
"""

import asyncio
import logging
import time

from google import genai
from google.genai import types

from pizzeria_bot.agents.prompts import SYSTEM_PROMPT
from pizzeria_bot.agents.tools import TOOLS, ToolRouter
from pizzeria_bot.audio.protocol import AudioIO
from pizzeria_bot.config import require_gemini_api_key, settings
from pizzeria_bot.logging_config import setup_logging

logger = logging.getLogger(__name__)

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BACKOFF_SECONDS = 2
IDLE_WATCHDOG_INTERVAL = 5.0

# Tools que hacen llamadas de red reales (no puro Python en memoria como
# las de domain/order.py) - ver _handle_tool_call.
_TOOLS_LENTAS = {"gestionar_queja"}


class CallEndedIntentionally(Exception):
    """Base para fines de llamada deliberados (no fallos de conexión) - no
    deben disparar reintentos en run_with_reconnect."""


class CallEndedByIdle(CallEndedIntentionally):
    """El cliente lleva demasiado tiempo en silencio - colgamos la llamada
    a propósito."""


class CallEndedByModel(CallEndedIntentionally):
    """El propio modelo decidió terminar la llamada (llamó a
    finalizar_llamada tras despedirse)."""


class PizzeriaCallSession:
    """Una llamada = una sesión con Gemini Live + un ToolRouter propio."""

    def __init__(self, client: genai.Client, audio_io: AudioIO, tool_router: ToolRouter) -> None:
        self.client = client
        self.audio_io = audio_io
        self.tool_router = tool_router
        self.session = None
        self._out_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._last_user_activity = time.monotonic()
        self._idle_checkin_sent = False
        # Se rellena cuando avisar_espera_incidencia tiene éxito, y se usa
        # justo después (ver _receive_and_play) para empujar al modelo a
        # llamar a gestionar_queja de verdad. Necesario porque, al
        # contrario de lo esperado, el modelo NO continúa solo tras decir
        # el mensaje de espera - simplemente se queda callado esperando
        # input nuevo del cliente (visto en producción: se quedaba más de
        # un minuto sin hacer nada hasta que el cliente volvía a hablar).
        self._nudge_gestionar_queja: dict | None = None

    async def _listen_microphone(self) -> None:
        count = 0
        while True:
            data = await self.audio_io.read_chunk()
            count += 1
            if count % 50 == 0 and len(data) >= 2 and logger.isEnabledFor(logging.DEBUG):
                # Amplitud pico del chunk PCM (16-bit); solo se calcula si DEBUG
                # está activo, para no gastar CPU en el hot path por nada.
                samples = [
                    int.from_bytes(data[i : i + 2], "little", signed=True)
                    for i in range(0, len(data), 2)
                ]
                peak = max(abs(s) for s in samples) if samples else 0
                logger.debug("Micrófono activo (chunk #%d enviado, amplitud pico: %d)", count, peak)
            await self._out_queue.put(data)

    async def _send_audio(self) -> None:
        count = 0
        while True:
            data = await self._out_queue.get()
            count += 1
            if count % 50 == 0:
                logger.debug("Audio enviado a Gemini (packet #%d)", count)
            await self.session.send_realtime_input(
                audio=types.Blob(data=data, mime_type=f"audio/pcm;rate={settings.send_sample_rate}")
            )

    async def _handle_tool_call(self, tool_call) -> None:
        # Gemini puede meter varias function calls en un mismo lote (mismo
        # response.tool_call) - y como send_tool_response() solo se llama
        # UNA VEZ al final, con TODAS las respuestas del lote juntas, el
        # modelo nunca "oye" el resultado de la primera antes de que la
        # segunda ya se haya ejecutado. Visto en producción: el modelo
        # metía avisar_espera_incidencia + gestionar_queja en el mismo
        # lote, así que el aviso de "dame un momento" y la resolución
        # final le llegaban juntos, 10 segundos después de la queja - la
        # tool de aviso quedaba completamente inútil (nunca se decía antes
        # de la búsqueda real, que es justo para lo que existe). Se
        # rechaza gestionar_queja si viene en el mismo lote que
        # avisar_espera_incidencia, forzando dos rondas separadas: el
        # modelo recibe el aviso solo, lo dice, y en su SIGUIENTE decisión
        # (una function call nueva, no en este mismo lote) llama a
        # gestionar_queja.
        nombres_en_este_lote = {fc.name for fc in tool_call.function_calls}
        function_responses = []
        for fc in tool_call.function_calls:
            args = dict(fc.args or {})
            if fc.name == "gestionar_queja" and "avisar_espera_incidencia" in nombres_en_este_lote:
                result = {
                    "ok": False,
                    "error": "Aún no has dicho el mensaje de avisar_espera_incidencia al "
                    "cliente en voz alta - dilo primero, y llama a gestionar_queja "
                    "después, en tu siguiente respuesta.",
                }
            elif fc.name in _TOOLS_LENTAS:
                # gestionar_queja hace llamadas de red reales (RAG + LLM
                # clasificador), varios segundos en total. Si se llama tal
                # cual (síncrono), bloquea el event loop entero durante ese
                # rato: se congelan el resto de tareas de esta misma sesión
                # (mic, altavoz, el watchdog de silencio...), no solo esta
                # tool call. Con to_thread corre en un hilo aparte y el loop
                # sigue vivo mientras se espera la respuesta.
                result = await asyncio.to_thread(self.tool_router.call, fc.name, args)
            else:
                result = self.tool_router.call(fc.name, args)
            logger.info("tool_call %s(%s) -> %s", fc.name, args, result)
            if fc.name == "avisar_espera_incidencia" and result.get("ok"):
                # Guarda los datos para empujar a gestionar_queja en cuanto
                # el modelo termine de decir este mensaje (ver
                # _receive_and_play) - no podemos hacerlo aquí mismo,
                # mandar texto nuevo mientras el modelo aún no ha hablado
                # el resultado de esta tool se leería como una
                # interrupción, no como una continuación.
                self._nudge_gestionar_queja = {
                    "nombre_cliente": args.get("nombre_cliente", ""),
                    "pedido": args.get("pedido", ""),
                }
            function_responses.append(
                types.FunctionResponse(id=fc.id, name=fc.name, response=result)
            )
        # Reinicia el reloj de "cliente en silencio" aquí, no solo cuando
        # habla: si no, el tiempo que tarda una tool lenta (gestionar_queja,
        # varios segundos) cuenta como silencio del cliente aunque esté
        # esperando pacientemente. Bug real visto en producción: al
        # terminar la tool, nada_pendiente pasaba a True y el reloj ya
        # llevaba acumulados esos segundos de proceso - el siguiente tick
        # del watchdog (cada 5s) superaba enseguida idle_post_confirm_
        # nudge_seconds y mandaba el aviso de "despídete" A MITAD de la
        # propia despedida del modelo, cortándola en seco (se veía en los
        # logs como un "barge-in" que en realidad no era del cliente).
        self._last_user_activity = time.monotonic()
        await self.session.send_tool_response(function_responses=function_responses)

    async def _receive_and_play(self) -> None:
        # session.receive() entrega los eventos de UN turno y se agota cuando
        # ese turno termina (turn_complete) — hay que volver a llamarlo para
        # cada turno nuevo. Sin este bucle exterior, tras el primer turno la
        # tarea terminaba silenciosamente y nadie volvía a leer del socket:
        # el mic seguía mandando audio pero no se transcribía ni respondía nada.
        while True:
            async for response in self.session.receive():
                # Cualquier cosa que llegue del modelo (audio, texto, una
                # tool call) cuenta como "la conversación sigue viva ahora
                # mismo" - reinicia el reloj de silencio aquí, no solo al
                # final del turno. Motivo real: el audio de una respuesta
                # puede seguir llegando varios segundos después de que la
                # transcripción de texto ya esté completa (la síntesis de
                # voz tarda su tiempo en transmitirse), así que el turno
                # como tal no había "terminado" (el bucle async for seguía
                # activo) cuando el watchdog comprobaba el reloj - y este
                # seguía marcando el último reinicio de mucho antes (la
                # tool call), disparando el aviso de "despídete" MIENTRAS
                # el modelo aún estaba hablando y cortándolo a media frase.
                self._last_user_activity = time.monotonic()
                if response.data is not None:
                    await self.audio_io.write_chunk(response.data)
                if response.tool_call:
                    try:
                        await self._handle_tool_call(response.tool_call)
                    except Exception:
                        # Una tool call mal formada no debe tirar la llamada entera:
                        # logueamos y seguimos, en vez de dejar que la excepción
                        # mate el TaskGroup y corte la sesión sin que el cliente oiga nada.
                        logger.exception("Error procesando tool_call, la sesión sigue")
                content = response.server_content
                if content and content.interrupted:
                    # El cliente empezó a hablar mientras el modelo aún estaba
                    # sonando por el altavoz (barge-in). El turno se corta a
                    # medias server-side - el resumen que se estaba diciendo
                    # puede haberse quedado incompleto, y el próximo turno del
                    # modelo puede parecer que "repite" cuando en realidad está
                    # terminando de decir lo que no llegó a decir.
                    logger.info("Turno del modelo INTERRUMPIDO por el cliente (barge-in).")
                if content and content.output_transcription:
                    logger.info("Modelo: %s", content.output_transcription.text)
                if content and content.input_transcription:
                    logger.info("Usuario: %s", content.input_transcription.text)
                    self._idle_checkin_sent = False
            if self._nudge_gestionar_queja is not None:
                # El turno donde el modelo dijo el mensaje de espera acaba
                # de terminar - ahora sí toca empujarlo a llamar a
                # gestionar_queja, con los mismos datos que ya usó en
                # avisar_espera_incidencia (que le dé él la descripción,
                # la tiene del resto de la conversación).
                datos = self._nudge_gestionar_queja
                self._nudge_gestionar_queja = None
                await self.session.send_realtime_input(
                    text=(
                        "(Ya le has dicho al cliente que esperase. Llama ahora mismo a "
                        f"gestionar_queja con nombre_cliente='{datos['nombre_cliente']}', "
                        f"pedido='{datos['pedido']}' y una descripcion clara del problema "
                        "que te ha contado - no le preguntes nada más antes, ya tienes todo "
                        "lo que hace falta.)"
                    )
                )
            if self.tool_router.debe_colgar:
                # El modelo ya llamó a finalizar_llamada en este turno (tras
                # despedirse). Esperamos a que el altavoz termine de sonar
                # ANTES de colgar, para no cortar la despedida a media frase,
                # y luego un margen extra con el micro aún abierto por si el
                # cliente responde con su propio "hasta luego" a la vez.
                logger.info("El modelo ha decidido terminar la llamada.")
                await self.audio_io.wait_until_speaker_drained()
                await asyncio.sleep(settings.hangup_grace_seconds)
                raise CallEndedByModel("finalizar_llamada invocada por el modelo")
            # Turno completo (o interrumpido): descarta audio de salida que
            # aún no se ha reproducido, para que el barge-in del usuario corte
            # limpio la respuesta anterior en vez de seguir sonando encima.
            self.audio_io.clear_output_buffer()

    async def _idle_watchdog(self) -> None:
        """Si el cliente lleva callado más de idle_checkin_seconds, le
        preguntamos si sigue ahí; si sigue sin decir nada hasta
        idle_hangup_seconds, colgamos. El aviso va por send_realtime_input
        (parámetro text), no por send_client_content — mezclar ese con el
        streaming continuo de audio es lo que el SDK desaconseja; text en
        send_realtime_input viaja por el mismo canal que el audio.

        Si ya no queda nada pendiente en la llamada (pedido confirmado, o
        una incidencia ya gestionada vía gestionar_queja - ver
        ToolRouter.nada_pendiente), no preguntamos "¿sigues ahí?" (no tiene
        sentido si ya no hay nada que esperar) — directamente le pedimos al
        modelo que se despida y cuelgue con finalizar_llamada, que ya espera
        a que el altavoz termine de sonar antes de cortar. Si ni con eso
        reacciona, cortamos sin despedida como último recurso. Sin esto, una
        llamada de incidencia que el modelo olvidó cerrar con
        finalizar_llamada caía en el mismo ciclo largo que una llamada
        todavía en curso, y acababa preguntando "¿sigues ahí?" de la nada
        después de que el cliente ya colgara mentalmente la conversación."""
        while True:
            await asyncio.sleep(IDLE_WATCHDOG_INTERVAL)
            idle_for = time.monotonic() - self._last_user_activity

            if self.tool_router.nada_pendiente:
                if idle_for > settings.idle_hangup_after_confirm_seconds:
                    raise CallEndedByIdle(
                        f"{idle_for:.0f}s de silencio con la llamada ya resuelta (el modelo no "
                        "colgó solo ni siquiera tras pedírselo)"
                    )
                if (
                    idle_for > settings.idle_post_confirm_nudge_seconds
                    and not self._idle_checkin_sent
                ):
                    logger.info(
                        "Nada pendiente, cliente en silencio %.0fs - pidiendo despedida.",
                        idle_for,
                    )
                    self._idle_checkin_sent = True
                    await self.session.send_realtime_input(
                        text="(Ya no queda nada pendiente en esta llamada y el cliente no "
                        "responde. NO repitas lo que ya le has contado. Despídete en una "
                        "frase corta y llama a finalizar_llamada ahora mismo.)"
                    )
                continue

            if idle_for > settings.idle_hangup_seconds:
                raise CallEndedByIdle(f"{idle_for:.0f}s sin actividad del cliente")

            if idle_for > settings.idle_checkin_seconds and not self._idle_checkin_sent:
                logger.info("Cliente en silencio %.0fs - preguntando si sigue ahí.", idle_for)
                self._idle_checkin_sent = True
                await self.session.send_realtime_input(
                    text="(El cliente lleva un rato en silencio. Pregúntale brevemente "
                    "si sigue ahí.)"
                )

    def _opening_prompt(self) -> str:
        """Instrucción interna para arrancar el turno del modelo sin esperar
        audio del cliente. Si el ToolRouter ya trae un pedido en curso (esta
        sesión viene de una reconexión), se lo contamos al modelo para que
        siga la conversación en vez de saludar como si fuera una llamada nueva."""
        order = self.tool_router.order
        hay_algo_ya = order.items or order.tipo_entrega or order.nombre_cliente or order.direccion
        if not hay_algo_ya and not order.telefono:
            return "(Empieza la llamada saludando al cliente.)"

        items_resumen = (
            ", ".join(f"[id {i.item_id}] {i.cantidad}x {i.pizza} ({i.tamano})" for i in order.items)
            or "ninguna pizza todavía"
        )
        return (
            "(Se ha reconectado la llamada tras un corte de red. No saludes de "
            f"nuevo desde cero. Pedido hasta ahora: {items_resumen}. "
            f"Tipo de entrega: {order.tipo_entrega or 'aún no lo tienes'}. "
            f"Nombre: {order.nombre_cliente or 'aún no lo tienes'}. "
            f"Dirección: {order.direccion or 'aún no la tienes'}. "
            f"Teléfono: {order.telefono or 'aún no lo tienes'}. "
            "Continúa la conversación con el cliente para terminar de tomar el pedido.)"
        )

    async def run(self) -> None:
        config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": SYSTEM_PROMPT,
            "tools": TOOLS,
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": "Puck"}},
                "language_code": "es-US",
            },
        }
        async with self.client.aio.live.connect(
            model=settings.gemini_model, config=config
        ) as session:
            self.session = session
            self._last_user_activity = time.monotonic()
            logger.info("Llamada conectada.")
            # Dispara el saludo inicial sin esperar a que el cliente hable primero.
            # send_client_content "prellena" la conversación; es el uso recomendado
            # por el SDK antes de arrancar el streaming en tiempo real con
            # send_realtime_input (mezclar ambos después de esto sí está desaconsejado).
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=self._opening_prompt())]),
                turn_complete=True,
            )
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._listen_microphone())
                tg.create_task(self._send_audio())
                tg.create_task(self._receive_and_play())
                tg.create_task(self._idle_watchdog())


async def run_with_reconnect(
    client: genai.Client, audio_io: AudioIO, tool_router: ToolRouter
) -> None:
    """
    Envuelve la sesión con reintentos con backoff. Un corte de red no debe
    tirar la llamada entera — solo la sesión de Gemini, y se reconecta
    manteniendo el mismo audio_io y tool_router (el pedido no se pierde).

    audio_io y tool_router se reciben como parámetros (no se crean aquí)
    para que esta misma función sirva tanto para la CLI local (LocalAudioIO,
    ver run() más abajo) como para el servidor Twilio (TwilioAudioIO, una
    instancia por llamada entrante, en server.py).
    """
    audio_io.open()
    attempt = 0
    try:
        while attempt < MAX_RECONNECT_ATTEMPTS:
            # except* no admite return/break/continue dentro del propio bloque
            # (PEP 654) - de ahí la bandera en vez de un return directo.
            call_ended_on_purpose = False
            try:
                session = PizzeriaCallSession(client, audio_io, tool_router)
                await session.run()
                return  # salida limpia (ej. Ctrl+C dentro del TaskGroup)
            except* CallEndedIntentionally as eg:
                for exc in eg.exceptions:
                    logger.info("Llamada terminada: %s", exc)
                call_ended_on_purpose = True
            except* Exception as eg:
                attempt += 1
                logger.error(
                    "Sesión caída (intento %d/%d): %s",
                    attempt,
                    MAX_RECONNECT_ATTEMPTS,
                    eg.exceptions,
                )
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    logger.error("Máximo de reintentos alcanzado, abortando.")
                    raise
                await asyncio.sleep(RECONNECT_BACKOFF_SECONDS * attempt)
            if call_ended_on_purpose:
                return
    finally:
        audio_io.close()


def run() -> None:
    """Punto de entrada de la CLI local (micro/altavoz del propio equipo).

    Import de LocalAudioIO deliberadamente perezoso, aquí dentro y no a
    nivel de módulo: LocalAudioIO tira de pyaudiowpatch (Windows-only), y
    server.py importa run_with_reconnect de este mismo módulo para el modo
    Twilio en Linux - un import a nivel de módulo rompería el servidor
    entero en cualquier plataforma sin pyaudiowpatch instalado."""
    from pizzeria_bot.audio.local_io import LocalAudioIO

    setup_logging(settings.log_level)
    try:
        client = genai.Client(api_key=require_gemini_api_key())
        audio_io = LocalAudioIO()
        # Vive fuera del bucle de reintentos de run_with_reconnect a propósito:
        # si hay un corte de red a mitad de pedido, reconectar no debe borrar
        # las pizzas que el cliente ya había confirmado.
        tool_router = ToolRouter()
        asyncio.run(run_with_reconnect(client, audio_io, tool_router))
    except KeyboardInterrupt:
        logger.info("Llamada terminada por el usuario.")


if __name__ == "__main__":
    run()
