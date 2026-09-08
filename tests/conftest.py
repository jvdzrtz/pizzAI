import pytest
from fastapi.testclient import TestClient

from pizzeria_bot import config, server


@pytest.fixture
def client(monkeypatch):
    """TestClient de server.app con las claves mínimas para que arranque
    (ver config.py: require_gemini_api_key/require_twilio_auth_token).
    Compartido por los tests de endpoints que no necesitan generar una
    firma Twilio real - test_server.py define su propia variante porque
    además firma peticiones HMAC contra un token concreto."""
    monkeypatch.setattr(config.settings, "gemini_api_key", "dummy-gemini-key")
    monkeypatch.setattr(config.settings, "twilio_auth_token", "dummy-auth-token")
    with TestClient(server.app) as c:
        yield c
