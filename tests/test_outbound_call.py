import pytest

from pizzeria_bot import config
from pizzeria_bot.outbound_call import build_call_params


@pytest.fixture
def with_twilio_number(monkeypatch):
    monkeypatch.setattr(config.settings, "twilio_phone_number", "+16016027245")


def test_build_call_params_construye_la_url_del_twiml(with_twilio_number):
    params = build_call_params("+34612345678", "https://xxxxx.devtunnels.ms")
    assert params["to"] == "+34612345678"
    assert params["from_"] == "+16016027245"
    assert params["url"] == "https://xxxxx.devtunnels.ms/voice/incoming"


def test_build_call_params_quita_barra_final_de_base_url(with_twilio_number):
    params = build_call_params("+34612345678", "https://xxxxx.devtunnels.ms/")
    assert params["url"] == "https://xxxxx.devtunnels.ms/voice/incoming"


def test_build_call_params_sin_numero_configurado_falla(monkeypatch):
    # Forzamos twilio_phone_number a None explícitamente - no basta con "no
    # monkeypatchearlo", porque en la máquina del usuario el .env real sí
    # lo tiene puesto y el test fallaría por el motivo equivocado.
    monkeypatch.setattr(config.settings, "twilio_phone_number", None)
    with pytest.raises(RuntimeError):
        build_call_params("+34612345678", "https://xxxxx.devtunnels.ms")
