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
        function_responses = []
        for fc in tool_call.function_calls:
            args = dict(fc.args or {})
            result = self.tool_router.call(fc.name, args)
            logger.info("tool_call %s(%s) -> %s", fc.name, args, result)
            function_responses.append(
                types.FunctionResponse(id=fc.id, name=fc.name, response=result)
            )
        await self.session.send_tool_response(function_responses=function_responses)

    async def _receive_and_play(self) -> None:
        # session.receive() entrega los eventos de UN turno y se agota cuando
        # ese turno termina (turn_complete) — hay que volver a llamarlo para
        # cada turno nuevo. Sin este bucle exterior, tras el primer turno la
        # tarea terminaba silenciosamente y nadie volvía a leer del socket:
        # el mic seguía mandando audio pero no se transcribía ni respondía nada.
        while True:
            async for response in self.session.receive():
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
                    self._last_user_activity = time.monotonic()
                    self._idle_checkin_sent = False
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

        Si el pedido ya está confirmado, no preguntamos "¿sigues ahí?" (no
        tiene sentido, ya no hay nada pendiente) — directamente le pedimos
        al modelo que se despida y cuelgue con finalizar_llamada, que ya
        espera a que el altavoz termine de sonar antes de cortar. Si ni con
        eso reacciona, cortamos sin despedida como último recurso."""
        while True:
            await asyncio.sleep(IDLE_WATCHDOG_INTERVAL)
            idle_for = time.monotonic() - self._last_user_activity

            if self.tool_router.order.confirmado:
                if idle_for > settings.idle_hangup_after_confirm_seconds:
                    raise CallEndedByIdle(
                        f"{idle_for:.0f}s de silencio tras confirmar (el modelo no colgó solo "
                        "ni siquiera tras pedírselo)"
                    )
                if (
                    idle_for > settings.idle_post_confirm_nudge_seconds
                    and not self._idle_checkin_sent
                ):
                    logger.info(
                        "Pedido confirmado, cliente en silencio %.0fs - pidiendo despedida.",
                        idle_for,
                    )
                    self._idle_checkin_sent = True
                    await self.session.send_realtime_input(
                        text="(El pedido ya está confirmado y el cliente no responde. "
                        "Despídete brevemente y cuelga la llamada llamando a "
                        "finalizar_llamada.)"
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
