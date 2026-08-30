"""
Conversión de audio entre el formato que usa Twilio Media Streams
(mu-law mono a 8kHz) y el PCM16 lineal que espera/devuelve la Live API de
Gemini. Funciones puras y sin estado - se pueden testear sin depender de
una conexión real a Twilio ni a Gemini.

El resampling usa audioop.ratecv (interpolación lineal) en vez de
scipy.signal.resample: es más que suficiente para voz telefónica (que ya
viene degradada por el propio mu-law a 8kHz) y evita añadir numpy/scipy
como dependencias pesadas solo para esto. audioop no está en la stdlib a
partir de Python 3.13 - lo provee el paquete audioop-lts.
"""

import audioop

SAMPLE_WIDTH = 2  # PCM16 = 2 bytes por muestra
CHANNELS = 1
TWILIO_SAMPLE_RATE = 8000


def mulaw_to_pcm16(mulaw: bytes) -> bytes:
    """mu-law 8-bit (como llega de Twilio) -> PCM16 lineal, mismo sample rate."""
    return audioop.ulaw2lin(mulaw, SAMPLE_WIDTH)


def pcm16_to_mulaw(pcm: bytes) -> bytes:
    """PCM16 lineal -> mu-law 8-bit (lo que espera Twilio)."""
    return audioop.lin2ulaw(pcm, SAMPLE_WIDTH)


def resample_pcm16(pcm: bytes, rate_in: int, rate_out: int) -> bytes:
    """Cambia el sample rate de un fragmento PCM16 mono."""
    if rate_in == rate_out:
        return pcm
    resampled, _ = audioop.ratecv(pcm, SAMPLE_WIDTH, CHANNELS, rate_in, rate_out, None)
    return resampled


def twilio_mulaw_to_gemini_pcm16(mulaw_8k: bytes, target_rate: int) -> bytes:
    """Pipeline de entrada: mu-law 8kHz (Twilio) -> PCM16 a target_rate (Gemini)."""
    pcm_8k = mulaw_to_pcm16(mulaw_8k)
    return resample_pcm16(pcm_8k, TWILIO_SAMPLE_RATE, target_rate)


def gemini_pcm16_to_twilio_mulaw(pcm: bytes, source_rate: int) -> bytes:
    """Pipeline de salida: PCM16 a source_rate (Gemini) -> mu-law 8kHz (Twilio)."""
    pcm_8k = resample_pcm16(pcm, source_rate, TWILIO_SAMPLE_RATE)
    return pcm16_to_mulaw(pcm_8k)
