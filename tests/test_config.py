import os

import pytest

from pizzeria_bot import config


def test_require_gemini_api_key_falla_si_no_hay_key(monkeypatch):
    monkeypatch.setattr(config.settings, "gemini_api_key", None)
    with pytest.raises(RuntimeError):
        config.require_gemini_api_key()


def test_require_gemini_api_key_devuelve_la_key_si_existe(monkeypatch):
    monkeypatch.setattr(config.settings, "gemini_api_key", "una-key-de-prueba")
    assert config.require_gemini_api_key() == "una-key-de-prueba"


def test_require_twilio_auth_token_falla_si_no_hay_token(monkeypatch):
    monkeypatch.setattr(config.settings, "twilio_auth_token", None)
    with pytest.raises(RuntimeError):
        config.require_twilio_auth_token()


def test_require_twilio_auth_token_devuelve_el_token_si_existe(monkeypatch):
    monkeypatch.setattr(config.settings, "twilio_auth_token", "un-token-de-prueba")
    assert config.require_twilio_auth_token() == "un-token-de-prueba"


def test_require_twilio_account_sid_falla_si_no_hay_sid(monkeypatch):
    monkeypatch.setattr(config.settings, "twilio_account_sid", None)
    with pytest.raises(RuntimeError):
        config.require_twilio_account_sid()


def test_require_twilio_account_sid_devuelve_el_sid_si_existe(monkeypatch):
    monkeypatch.setattr(config.settings, "twilio_account_sid", "AC-de-prueba")
    assert config.require_twilio_account_sid() == "AC-de-prueba"


def test_require_twilio_phone_number_falla_si_no_hay_numero(monkeypatch):
    monkeypatch.setattr(config.settings, "twilio_phone_number", None)
    with pytest.raises(RuntimeError):
        config.require_twilio_phone_number()


def test_require_twilio_phone_number_devuelve_el_numero_si_existe(monkeypatch):
    monkeypatch.setattr(config.settings, "twilio_phone_number", "+16016027245")
    assert config.require_twilio_phone_number() == "+16016027245"


def test_langsmith_desactivado_no_toca_el_entorno(monkeypatch):
    # delenv primero: el .env real de este repo puede tener
    # LANGSMITH_TRACING=true de verdad, y _propagar_langsmith ya lo habrá
    # volcado a os.environ al importar config por primera vez en este
    # proceso de test - hay que partir de limpio para que la aserción de
    # "no toca nada" signifique algo.
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)

    # Settings de mentira, no el singleton real - así no depende de lo que
    # haya en el .env de quien corra los tests.
    config._propagar_langsmith(config.Settings(langsmith_tracing=False))

    assert "LANGSMITH_TRACING" not in os.environ
    assert "LANGSMITH_API_KEY" not in os.environ


def test_langsmith_activado_propaga_las_variables_a_os_environ(monkeypatch):
    # pydantic-settings solo carga .env hacia sus propios campos, no lo
    # vuelca a os.environ - por eso config.py tiene que hacerlo a mano
    # (ver _propagar_langsmith), y por eso esto no se puede comprobar solo
    # con monkeypatch.setattr(settings, ...) como el resto de tests de
    # este archivo.
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)

    config._propagar_langsmith(
        config.Settings(
            langsmith_tracing=True,
            langsmith_api_key="una-key-de-prueba",
            langsmith_project="mi-proyecto-de-prueba",
        )
    )

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "una-key-de-prueba"
    assert os.environ["LANGSMITH_PROJECT"] == "mi-proyecto-de-prueba"
