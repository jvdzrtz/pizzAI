import os

# Se ejecuta ANTES de importar pizzeria_bot.config (más abajo) a propósito:
# config.py lee LANGSMITH_TRACING de .env en cuanto se importa por primera
# vez, y una variable de entorno real tiene precedencia sobre el .env
# (comportamiento estándar de pydantic-settings) - así forzamos que quede
# desactivado para TODA la sesión de tests, pase lo que pase en el .env
# real de quien los corra. Sin esto, un pytest con LANGSMITH_TRACING=true
# en .env manda trazas reales de los tests (incluidas las que usan LLMs
# falsos a propósito, como test_complaint_graph.py) al proyecto de
# LangSmith de verdad - ya nos pasó una vez, ensuciando el histórico con
# ejecuciones que no representan nada real.
os.environ["LANGSMITH_TRACING"] = "false"

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
