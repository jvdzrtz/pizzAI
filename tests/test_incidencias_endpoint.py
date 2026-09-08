import pytest
from fastapi.testclient import TestClient

from pizzeria_bot import config, server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config.settings, "gemini_api_key", "dummy-gemini-key")
    monkeypatch.setattr(config.settings, "twilio_auth_token", "dummy-auth-token")
    with TestClient(server.app) as c:
        yield c


def test_incidencias_pendientes_vacio(client, monkeypatch):
    monkeypatch.setattr(server, "listar_incidencias_pendientes", list)

    response = client.get("/incidencias/pendientes")

    assert response.status_code == 200
    assert response.json() == []


def test_incidencias_pendientes_devuelve_las_escaladas(client, monkeypatch):
    incidencia = {
        "id": "abc-123",
        "nombre_cliente": "Jorge",
        "pedido": "1 margarita mediana",
        "tipo_incidencia": "cobro incorrecto",
        "decision_tomada": "Derivada a revisión humana, sin compensación automática.",
        "estado": "pendiente_revision",
    }
    monkeypatch.setattr(server, "listar_incidencias_pendientes", lambda: [incidencia])

    response = client.get("/incidencias/pendientes")

    assert response.status_code == 200
    assert response.json() == [incidencia]
