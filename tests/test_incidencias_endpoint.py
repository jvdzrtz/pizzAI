from pizzeria_bot import server

# La fixture `client` vive en tests/conftest.py - compartida con
# test_faq_endpoint.py, ambos la usan tal cual sin cambios.


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
