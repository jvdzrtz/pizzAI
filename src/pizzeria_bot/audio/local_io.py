import asyncio
import logging
import threading
import time

import pyaudiowpatch as pyaudio

from pizzeria_bot.config import settings

logger = logging.getLogger(__name__)

FORMAT = pyaudio.paInt16
CHANNELS = 1

MIC_STALL_TIMEOUT = 3.0  # segundos sin callback del mic antes de forzar reinicio del stream
MIC_WATCHDOG_INTERVAL = 1.0


def _find_device_index(
    pa: pyaudio.PyAudio, name_query: str | None, is_input: bool, sample_rate: int
) -> int | None:
    if not name_query:
        return None

    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        channels = info["maxInputChannels"] if is_input else info["maxOutputChannels"]
        if channels > 0 and name_query.lower() in info["name"].lower():
            try:
                kwargs = (
                    {"input_device": i, "input_channels": CHANNELS, "input_format": FORMAT}
                    if is_input
                    else {"output_device": i, "output_channels": CHANNELS, "output_format": FORMAT}
                )
                if pa.is_format_supported(sample_rate, **kwargs):
                    return i
            except ValueError as e:
                logger.debug(
                    "Dispositivo %d (%s) no soporta rate=%d: %s", i, info["name"], sample_rate, e
                )
                continue

    return None


class LocalAudioIO:
    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._pa = pyaudio.PyAudio()
        self._loop = loop
        self._mic_stream: pyaudio.Stream | None = None
        self._speaker_stream: pyaudio.Stream | None = None

        self._input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._output_buffer = bytearray()
        self._output_lock = threading.Lock()
        self._mic_callback_count = 0

        self._mic_stream_kwargs: dict | None = None
        self._last_mic_callback_at = time.monotonic()
        self._mic_restart_count = 0
        self._watchdog_task: asyncio.Task | None = None

    def open(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        if loop is not None:
            self._loop = loop
        elif self._loop is None:
            self._loop = asyncio.get_running_loop()

        # Resolver índice de entrada (Micrófono)
        input_idx = settings.input_device_index
        if input_idx is None:
            input_idx = _find_device_index(
                self._pa,
                settings.input_device_name,
                is_input=True,
                sample_rate=settings.send_sample_rate,
            )

        # Resolver índice de salida (Altavoces)
        output_idx = settings.output_device_index
        if output_idx is None:
            output_idx = _find_device_index(
                self._pa,
                settings.output_device_name,
                is_input=False,
                sample_rate=settings.receive_sample_rate,
            )

        mic_info = (
            self._pa.get_device_info_by_index(input_idx)
            if input_idx is not None
            else self._pa.get_default_input_device_info()
        )
        spk_info = (
            self._pa.get_device_info_by_index(output_idx)
            if output_idx is not None
            else self._pa.get_default_output_device_info()
        )

        logger.info("Micrófono seleccionado: index=%s (%s)", mic_info["index"], mic_info["name"])
        logger.info("Altavoz seleccionado: index=%s (%s)", spk_info["index"], spk_info["name"])

        self._mic_stream_kwargs = {
            "format": FORMAT,
            "channels": CHANNELS,
            "rate": settings.send_sample_rate,
            "input": True,
            "input_device_index": mic_info["index"],
            "frames_per_buffer": settings.chunk_size,
            "stream_callback": self._mic_callback,
        }
        self._mic_stream = self._pa.open(**self._mic_stream_kwargs)

        self._speaker_stream = self._pa.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=settings.receive_sample_rate,
            output=True,
            output_device_index=spk_info["index"],
            frames_per_buffer=settings.chunk_size,
            stream_callback=self._speaker_callback,
        )

        self._last_mic_callback_at = time.monotonic()
        self._mic_stream.start_stream()
        self._speaker_stream.start_stream()
        self._watchdog_task = self._loop.create_task(self._mic_watchdog())

    def _mic_callback(self, in_data, frame_count, time_info, status_flags):
        if status_flags:
            logger.warning(
                "mic callback status_flags=%s (overflow/underflow del driver)", status_flags
            )
        self._last_mic_callback_at = time.monotonic()
        self._mic_callback_count += 1
        if self._mic_callback_count % 50 == 0:
            # Log directo desde el hilo de PortAudio, sin pasar por la cola/event loop:
            # si esto deja de aparecer, PortAudio dejó de invocar el callback (fallo de
            # driver/hardware). Útil para diagnosticar cuelgues del stream; a DEBUG
            # porque en marcha normal es puro ruido (dispara cada ~3s).
            logger.debug("mic callback #%d (driver-level, vivo)", self._mic_callback_count)
        if in_data and self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._input_queue.put_nowait, in_data)
        return (None, pyaudio.paContinue)

    async def _mic_watchdog(self) -> None:
        """Si PortAudio deja de invocar _mic_callback (driver colgado tras
        arrancar la reproducción en un dispositivo full-duplex compartido),
        forzamos cierre + reapertura del stream de entrada en caliente."""
        while True:
            await asyncio.sleep(MIC_WATCHDOG_INTERVAL)
            stalled_for = time.monotonic() - self._last_mic_callback_at
            if stalled_for > MIC_STALL_TIMEOUT:
                self._mic_restart_count += 1
                logger.warning(
                    "Mic sin callbacks durante %.1fs — reiniciando stream de entrada (reinicio #%d)",
                    stalled_for,
                    self._mic_restart_count,
                )
                await asyncio.to_thread(self._restart_mic_stream)

    def _restart_mic_stream(self) -> None:
        assert self._mic_stream_kwargs is not None
        try:
            if self._mic_stream is not None:
                self._mic_stream.stop_stream()
                self._mic_stream.close()
        except Exception:
            logger.exception("Error cerrando el stream de mic antes de reiniciar")
        self._mic_stream = self._pa.open(**self._mic_stream_kwargs)
        self._last_mic_callback_at = time.monotonic()
        self._mic_stream.start_stream()

    def _speaker_callback(self, in_data, frame_count, time_info, status_flags):
        if status_flags:
            logger.warning(
                "speaker callback status_flags=%s (overflow/underflow del driver)", status_flags
            )
        bytes_needed = frame_count * 2 * CHANNELS
        with self._output_lock:
            if len(self._output_buffer) >= bytes_needed:
                data = bytes(self._output_buffer[:bytes_needed])
                del self._output_buffer[:bytes_needed]
            else:
                data = bytes(self._output_buffer)
                self._output_buffer.clear()
                data += b"\x00" * (bytes_needed - len(data))
        return (data, pyaudio.paContinue)

    async def read_chunk(self) -> bytes:
        return await self._input_queue.get()

    async def write_chunk(self, data: bytes) -> None:
        with self._output_lock:
            self._output_buffer.extend(data)

    def clear_output_buffer(self) -> None:
        with self._output_lock:
            self._output_buffer.clear()

    def close(self) -> None:
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        for stream in (self._mic_stream, self._speaker_stream):
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    logger.debug(
                        "Error cerrando stream de audio (ignorado, ya estamos cerrando)",
                        exc_info=True,
                    )
        self._pa.terminate()
