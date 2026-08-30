import asyncio
import base64

from pizzeria_bot.audio import codecs
from pizzeria_bot.audio.twilio_io import TwilioAudioIO


class FakeTwilioWebSocket:
    """Sustituye al WebSocket real de Starlette en los tests - solo
    necesita el método send_json que TwilioAudioIO realmente usa."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


def test_push_inbound_mulaw_llega_a_read_chunk_como_pcm16():
    async def _run():
        ws = FakeTwilioWebSocket()
        audio_io = TwilioAudioIO(ws)

        mulaw = codecs.pcm16_to_mulaw(b"\x00\x10" * 160)
        await audio_io.push_inbound_mulaw(base64.b64encode(mulaw).decode("ascii"))

        chunk = await audio_io.read_chunk()
        assert isinstance(chunk, bytes)
        assert len(chunk) > 0

    asyncio.run(_run())


def test_write_chunk_sin_stream_sid_no_revienta():
    # Antes de que llegue el evento "start" de Twilio no hay streamSid
    # todavía - no debe fallar, simplemente descarta el audio.
    async def _run():
        ws = FakeTwilioWebSocket()
        audio_io = TwilioAudioIO(ws)
        await audio_io.write_chunk(b"\x00\x10" * 480)
        assert ws.sent == []

    asyncio.run(_run())


def test_write_chunk_envia_evento_media_con_stream_sid():
    async def _run():
        ws = FakeTwilioWebSocket()
        audio_io = TwilioAudioIO(ws)
        audio_io.set_stream_sid("MZ123")

        await audio_io.write_chunk(b"\x00\x10" * 480)

        assert len(ws.sent) == 1
        msg = ws.sent[0]
        assert msg["event"] == "media"
        assert msg["streamSid"] == "MZ123"
        assert "payload" in msg["media"]
        # el payload debe ser base64 válido y decodificar a bytes no vacíos
        decoded = base64.b64decode(msg["media"]["payload"])
        assert len(decoded) > 0

    asyncio.run(_run())


def test_clear_output_buffer_envia_evento_clear():
    async def _run():
        ws = FakeTwilioWebSocket()
        audio_io = TwilioAudioIO(ws)
        audio_io.set_stream_sid("MZ123")

        audio_io.clear_output_buffer()
        # clear_output_buffer lanza una tarea de fondo (es síncrono, misma
        # interfaz que LocalAudioIO) - hay que cederle el control un instante.
        await asyncio.sleep(0)

        assert any(msg["event"] == "clear" for msg in ws.sent)

    asyncio.run(_run())


def test_wait_until_speaker_drained_no_espera_si_no_se_ha_enviado_nada():
    async def _run():
        ws = FakeTwilioWebSocket()
        audio_io = TwilioAudioIO(ws)
        # No debe colgarse esperando algo que nunca se envió.
        await asyncio.wait_for(audio_io.wait_until_speaker_drained(timeout=1.0), timeout=1.0)

    asyncio.run(_run())


def test_wait_until_speaker_drained_espera_lo_que_dura_el_audio_enviado():
    async def _run():
        ws = FakeTwilioWebSocket()
        audio_io = TwilioAudioIO(ws)
        audio_io.set_stream_sid("MZ123")

        # write_chunk asume PCM16 a settings.receive_sample_rate (24000 Hz)
        # de entrada; 24000 muestras -> ~1 segundo de audio tras convertir a
        # mu-law 8kHz.
        await audio_io.write_chunk(b"\x00\x10" * 24000)

        loop = asyncio.get_event_loop()
        start = loop.time()
        await asyncio.wait_for(audio_io.wait_until_speaker_drained(timeout=5.0), timeout=5.0)
        elapsed = loop.time() - start

        assert elapsed > 0.5  # de verdad esperó, no fue un no-op

    asyncio.run(_run())
