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
