from pizzeria_bot import server

# La fixture `client` vive en tests/conftest.py - compartida con
# test_incidencias_endpoint.py, ambos la usan tal cual sin cambios.


def test_faq_preguntar_devuelve_la_respuesta_del_rag(client, monkeypatch):
    monkeypatch.setattr(
        server, "responder_faq", lambda pregunta: f"respuesta simulada para: {pregunta}"
    )

    response = client.post("/faq/preguntar", json={"pregunta": "¿Hacéis reparto a domicilio?"})

    assert response.status_code == 200
    assert response.json() == {
        "respuesta": "respuesta simulada para: ¿Hacéis reparto a domicilio?"
    }


def test_faq_preguntar_rechaza_pregunta_vacia(client):
    response = client.post("/faq/preguntar", json={"pregunta": "   "})

    assert response.status_code == 400


def test_faq_preguntar_devuelve_502_si_responder_faq_falla(client, monkeypatch):
    def _revienta(pregunta: str) -> str:
        raise RuntimeError("fallo simulado del RAG")

    monkeypatch.setattr(server, "responder_faq", _revienta)

    response = client.post("/faq/preguntar", json={"pregunta": "¿Cuál es el horario?"})

    assert response.status_code == 502
