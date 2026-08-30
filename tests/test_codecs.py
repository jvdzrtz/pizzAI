import math
import struct

from pizzeria_bot.audio import codecs


def _sine_pcm16(n_samples: int, amplitude: int = 5000) -> bytes:
    """Genera n_samples de una onda senoidal en PCM16 para tests, en vez de
    silencio (todo ceros) - así se ejercitan de verdad los conversores en
    vez de solo comprobar el caso trivial."""
    samples = [int(amplitude * math.sin(i / 5)) for i in range(n_samples)]
    return struct.pack(f"<{n_samples}h", *samples)


def test_mulaw_pcm16_roundtrip_preserves_signal_shape():
    # mu-law es compresión con pérdida, no hay igualdad exacta, pero el
    # resultado no debe quedar en silencio ni desbordar el rango de 16 bits.
    original = _sine_pcm16(160)
    mulaw = codecs.pcm16_to_mulaw(original)
    recovered = codecs.mulaw_to_pcm16(mulaw)

    assert len(mulaw) == 160  # mu-law: 1 byte por muestra
    assert len(recovered) == len(original)

    original_samples = struct.unpack("<160h", original)
    recovered_samples = struct.unpack("<160h", recovered)
    # La diferencia media debe ser pequeña comparada con la amplitud de la
    # señal (mu-law tiene más resolución cerca de cero, menos en picos).
    avg_error = (
        sum(abs(a - b) for a, b in zip(original_samples, recovered_samples, strict=True)) / 160
    )
    assert avg_error < 500


def test_resample_misma_tasa_no_cambia_nada():
    pcm = _sine_pcm16(100)
    assert codecs.resample_pcm16(pcm, 16000, 16000) == pcm


def test_resample_8k_a_16k_duplica_aproximadamente_el_tamano():
    pcm_8k = _sine_pcm16(160)  # 20ms a 8kHz
    pcm_16k = codecs.resample_pcm16(pcm_8k, 8000, 16000)
    assert abs(len(pcm_16k) - len(pcm_8k) * 2) <= 4


def test_resample_24k_a_8k_reduce_aproximadamente_a_un_tercio():
    pcm_24k = _sine_pcm16(480)  # 20ms a 24kHz
    pcm_8k = codecs.resample_pcm16(pcm_24k, 24000, 8000)
    assert abs(len(pcm_8k) - len(pcm_24k) // 3) <= 4


def test_pipeline_entrada_twilio_a_gemini():
    # 20ms de audio de Twilio (mu-law 8kHz) -> PCM16 al rate que usa Gemini
    # para recibir audio (send_sample_rate, 16kHz).
    mulaw_8k = codecs.pcm16_to_mulaw(_sine_pcm16(160))
    pcm16_for_gemini = codecs.twilio_mulaw_to_gemini_pcm16(mulaw_8k, 16000)

    # 160 muestras a 8kHz -> ~320 muestras a 16kHz -> ~640 bytes PCM16
    assert abs(len(pcm16_for_gemini) - 640) <= 8


def test_pipeline_salida_gemini_a_twilio():
    # 20ms de audio de Gemini (PCM16 a 24kHz, receive_sample_rate) -> mu-law
    # 8kHz para reenviar a Twilio.
    pcm_24k = _sine_pcm16(480)
    mulaw_for_twilio = codecs.gemini_pcm16_to_twilio_mulaw(pcm_24k, 24000)

    # 480 muestras a 24kHz -> ~160 muestras a 8kHz -> 160 bytes mu-law
    assert abs(len(mulaw_for_twilio) - 160) <= 4


def test_pipeline_completo_ida_y_vuelta_no_esta_en_silencio():
    # Verifica que el pipeline completo (entrada + salida) no colapsa la
    # señal a silencio en ningún punto de la cadena.
    original = _sine_pcm16(160, amplitude=8000)
    mulaw_8k = codecs.pcm16_to_mulaw(original)

    pcm_for_gemini = codecs.twilio_mulaw_to_gemini_pcm16(mulaw_8k, 16000)
    assert any(b != 0 for b in pcm_for_gemini)

    mulaw_back = codecs.gemini_pcm16_to_twilio_mulaw(pcm_for_gemini, 16000)
    assert any(b != 0 for b in mulaw_back)
