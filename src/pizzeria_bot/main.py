import asyncio
import logging

from google import genai
from google.genai import types

from pizzeria_bot.agents.prompts import SYSTEM_PROMPT
from pizzeria_bot.agents.tools import TOOLS, ToolRouter
from pizzeria_bot.audio.local_io import LocalAudioIO
from pizzeria_bot.config import settings
from pizzeria_bot.logging_config import setup_logging

logger = logging.getLogger(__name__)

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BACKOFF_SECONDS = 2


class PizzeriaCallSession:
    """Una llamada = una sesión con Gemini Live + un ToolRouter propio."""

    def __init__(
        self, client: genai.Client, audio_io: LocalAudioIO, tool_router: ToolRouter
    ) -> None:
        self.client = client
        self.audio_io = audio_io
        self.tool_router = tool_router
        self.session = None
        self._out_queue: asyncio.Queue[bytes] = asyncio.Queue()

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
                if content and content.output_transcription:
                    logger.info("Modelo: %s", content.output_transcription.text)
                if content and content.input_transcription:
                    logger.info("Usuario: %s", content.input_transcription.text)
            # Turno completo (o interrumpido): descarta audio de salida que
            # aún no se ha reproducido, para que el barge-in del usuario corte
            # limpio la respuesta anterior en vez de seguir sonando encima.
            self.audio_io.clear_output_buffer()

    def _opening_prompt(self) -> str:
        """Instrucción interna para arrancar el turno del modelo sin esperar
        audio del cliente. Si el ToolRouter ya trae un pedido en curso (esta
        sesión viene de una reconexión), se lo contamos al modelo para que
        siga la conversación en vez de saludar como si fuera una llamada nueva."""
        order = self.tool_router.order
        if not order.items and not order.direccion and not order.telefono:
            return "(Empieza la llamada saludando al cliente.)"

        items_resumen = (
            ", ".join(f"{i.cantidad}x {i.pizza} ({i.tamano})" for i in order.items)
            or "ninguna pizza todavía"
        )
        return (
            "(Se ha reconectado la llamada tras un corte de red. No saludes de "
            f"nuevo desde cero. Pedido hasta ahora: {items_resumen}. "
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


async def run_with_reconnect() -> None:
    """
    Envuelve la sesión con reintentos con backoff. Un corte de red no debe
    tirar el proceso entero — solo la sesión actual, y se reconecta.
    """
    client = genai.Client(api_key=settings.gemini_api_key)
    audio_io = LocalAudioIO()
    audio_io.open()
    # Vive fuera del bucle de reintentos a propósito: si hay un corte de red
    # a mitad de pedido, reconectar no debe borrar las pizzas que el cliente
    # ya había confirmado.
    tool_router = ToolRouter()

    attempt = 0
    try:
        while attempt < MAX_RECONNECT_ATTEMPTS:
            try:
                session = PizzeriaCallSession(client, audio_io, tool_router)
                await session.run()
                return  # salida limpia (ej. Ctrl+C dentro del TaskGroup)
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
    finally:
        audio_io.close()


def run() -> None:
    setup_logging()
    try:
        asyncio.run(run_with_reconnect())
    except KeyboardInterrupt:
        logger.info("Llamada terminada por el usuario.")


if __name__ == "__main__":
    run()
