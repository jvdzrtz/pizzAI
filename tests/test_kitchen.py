import asyncio

import pytest
from fastapi.testclient import TestClient

from pizzeria_bot import config
from pizzeria_bot.agents.tools import ToolRouter
from pizzeria_bot.kitchen.store import store
from pizzeria_bot.server import app


class FakeKitchenScreen:
    """Simula una pantalla de cocina conectada - solo necesita send_json,
    igual que TwilioAudioIO simula el WebSocket real de Twilio en sus tests."""

    def __init__(self) -> None:
        self.recibidos: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.recibidos.append(data)


@pytest.fixture(autouse=True)
def _store_limpio():
    """kitchen_store.store es un singleton a nivel de módulo (a propósito:
    es el mismo store que usa toda la app) - sin limpiarlo entre tests, los
    tickets de un test se colarían en el snapshot del siguiente."""
    store._tickets.clear()
    store._clientes.clear()
    yield
    store._tickets.clear()
    store._clientes.clear()


def _confirmar_pedido_de_prueba(router: ToolRouter) -> dict:
    router.call("anadir_item_pedido", {"pizza": "pepperoni", "tamano": "familiar"})
    router.call("fijar_tipo_entrega", {"tipo": "domicilio"})
    router.call(
        "fijar_datos_cliente",
        {"nombre": "Javi", "direccion": "Avenida de las Ciencias, 35", "telefono": "717700856"},
    )
    return router.call("confirmar_pedido", {})


def test_anadir_ticket_sin_event_loop_no_revienta():
    # ToolRouter.call() es síncrono y test_tools.py lo llama así, sin
    # ningún loop de asyncio corriendo - anadir_ticket debe degradarse con
    # gracia (guarda el ticket igual, simplemente no hay a quién avisar).
    router = ToolRouter()
    resultado = _confirmar_pedido_de_prueba(router)

    assert resultado["ok"] is True
    assert len(store.snapshot()) == 1


def test_confirmar_pedido_via_toolrouter_emite_ticket_por_websocket():
    """Reproduce la estructura real de producción: ToolRouter.call() se
    invoca de forma síncrona pero DESDE DENTRO de una corrutina que ya se
    está ejecutando en un loop (igual que main.py: _handle_tool_call) -
    así asyncio.get_running_loop() dentro de kitchen_store.anadir_ticket()
    encuentra un loop de verdad y el ticket llega en vivo."""

    async def _run() -> None:
        pantalla = FakeKitchenScreen()
        store.registrar_cliente(pantalla)

        router = ToolRouter()
        resultado = _confirmar_pedido_de_prueba(router)
        assert resultado["ok"] is True

        # anadir_ticket lanza el envío como tarea de fondo (create_task) -
        # hay que ceder el control un instante para que llegue a correr.
        await asyncio.sleep(0.05)

        assert len(pantalla.recibidos) == 1
        evento = pantalla.recibidos[0]
        assert evento["event"] == "nuevo_ticket"
        assert evento["ticket"]["resumen"]["nombre_cliente"] == "Javi"
        assert evento["ticket"]["resumen"]["telefono"] == "717700856"

        store.desregistrar_cliente(pantalla)

    asyncio.run(_run())


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config.settings, "gemini_api_key", "dummy-gemini-key")
    monkeypatch.setattr(config.settings, "twilio_auth_token", "dummy-auth-token")
    with TestClient(app) as c:
        yield c


def test_kitchen_page_devuelve_html(client):
    response = client.get("/kitchen")

    assert response.status_code == 200
    assert "Cocina" in response.text


def test_kitchen_ws_manda_snapshot_vacio_si_no_hay_tickets(client):
    with client.websocket_connect("/kitchen/ws") as ws:
        snapshot = ws.receive_json()

        assert snapshot["event"] == "snapshot"
        assert snapshot["tickets"] == []


def test_kitchen_ws_manda_snapshot_con_tickets_ya_confirmados(client):
    router = ToolRouter()
    _confirmar_pedido_de_prueba(router)

    with client.websocket_connect("/kitchen/ws") as ws:
        snapshot = ws.receive_json()

        assert snapshot["event"] == "snapshot"
        assert len(snapshot["tickets"]) == 1
        assert snapshot["tickets"][0]["resumen"]["nombre_cliente"] == "Javi"
