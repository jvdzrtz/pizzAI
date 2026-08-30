"""
AudioIO que en vez de leer/escribir hardware local, recibe y envía audio
por el WebSocket de un Media Stream de Twilio - misma interfaz async que
LocalAudioIO (ver audio/protocol.py), así PizzeriaCallSession no necesita
saber cuál de las dos está usando.
"""

import asyncio
import base64
import logging
import time
from typing import Any, Protocol

from pizzeria_bot.audio import codecs
from pizzeria_bot.config import settings

logger = logging.getLogger(__name__)


class _SendsJSON(Protocol):
    async def send_json(self, data: Any) -> None: ...


class TwilioAudioIO:
    def __init__(self, websocket: _SendsJSON) -> None:
        self._ws = websocket
        self._stream_sid: str | None = None
        self._input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        # Estimación de cuándo Twilio habrá terminado de reproducir todo lo
        # que le hemos mandado hasta ahora - no hay un buffer local que
        # consultar (el audio ya se envió), así que lo llevamos por tiempo.
        self._estimated_playback_done_at = time.monotonic()

    def set_stream_sid(self, stream_sid: str) -> None:
        self._stream_sid = stream_sid

    def open(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        # Nada que abrir: el audio ya fluye por el WebSocket que gestiona
        # server.py. Existe solo para cumplir la interfaz AudioIO.
        pass

    def close(self) -> None:
        # El propio servidor cierra el WebSocket al terminar la llamada.
        pass

    async def push_inbound_mulaw(self, mulaw_b64: str) -> None:
        """Llamado por el bucle del WebSocket de server.py cuando llega un
        evento 'media' de Twilio (audio del cliente telefónico)."""
        mulaw = base64.b64decode(mulaw_b64)
        pcm16 = codecs.twilio_mulaw_to_gemini_pcm16(mulaw, settings.send_sample_rate)
        await self._input_queue.put(pcm16)

    async def read_chunk(self) -> bytes:
        return await self._input_queue.get()

    async def write_chunk(self, data: bytes) -> None:
        if self._stream_sid is None:
            logger.warning("write_chunk antes de recibir streamSid de Twilio, se descarta")
            return

        mulaw = codecs.gemini_pcm16_to_twilio_mulaw(data, settings.receive_sample_rate)
        payload = base64.b64encode(mulaw).decode("ascii")
        async with self._send_lock:
            await self._ws.send_json(
                {
                    "event": "media",
                    "streamSid": self._stream_sid,
                    "media": {"payload": payload},
                }
            )

        # mu-law a 8kHz = 8000 bytes/segundo (1 byte por muestra) - así
        # estimamos cuándo terminará de sonar esto en el teléfono del cliente.
        duration = len(mulaw) / codecs.TWILIO_SAMPLE_RATE
        base = max(time.monotonic(), self._estimated_playback_done_at)
        self._estimated_playback_done_at = base + duration

    def clear_output_buffer(self) -> None:
        self._estimated_playback_done_at = time.monotonic()
        if self._stream_sid is None:
            return
        # Twilio soporta un evento "clear" para vaciar su cola de audio
        # pendiente - es el equivalente al barge-in local. clear_output_buffer
        # es síncrono (misma interfaz que LocalAudioIO), así que lanzamos el
        # envío como tarea de fondo en vez de bloquear.
        asyncio.create_task(self._send_clear_event())

    async def _send_clear_event(self) -> None:
        try:
            await self._ws.send_json({"event": "clear", "streamSid": self._stream_sid})
        except Exception:
            logger.debug("No se pudo enviar evento 'clear' a Twilio", exc_info=True)

    async def wait_until_speaker_drained(
        self, timeout: float = 10.0, poll_interval: float = 0.2
    ) -> None:
        remaining = self._estimated_playback_done_at - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(min(remaining, timeout))
