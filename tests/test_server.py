import base64
import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pizzeria_bot import config
from pizzeria_bot.server import _public_host, app

TEST_AUTH_TOKEN = "test-auth-token-no-es-real"


def _twilio_signature(url: str, params: dict) -> str:
    """Replica el algoritmo de firma de Twilio (documentado públicamente:
    HMAC-SHA1 sobre la URL + parámetros ordenados alfabéticamente,
    en base64) para poder generar firmas válidas en los tests sin depender
    de internals de la librería oficial ni de una cuenta Twilio real."""
    data = url
    for key in sorted(params.keys()):
        data += key + str(params[key])
    mac = hmac.new(TEST_AUTH_TOKEN.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config.settings, "gemini_api_key", "dummy-gemini-key")
    monkeypatch.setattr(config.settings, "twilio_auth_token", TEST_AUTH_TOKEN)
    with TestClient(app) as c:
        yield c


def test_public_host_prefiere_x_forwarded_host():
    # Túneles como devtunnel (a veces también ngrok) reescriben la
    # cabecera Host a algo interno ("localhost:8000") antes de que la
    # petición llegue a la app, pero sí reenvían el host público real en
    # X-Forwarded-Host - hay que usar ese, o la firma de Twilio nunca
    # cuadra y el TwiML apunta a una dirección inalcanzable desde fuera.
    headers = {"host": "localhost:8000", "x-forwarded-host": "bj8mz1r7-8000.uks1.devtunnels.ms"}
    assert _public_host(headers) == "bj8mz1r7-8000.uks1.devtunnels.ms"


def test_public_host_usa_host_si_no_hay_x_forwarded_host():
    headers = {"host": "testserver"}
    assert _public_host(headers) == "testserver"


def test_voice_incoming_detras_de_tunel_con_host_interno_reescrito(client):
    # Reproduce el caso real: el túnel entrega Host=localhost:8000 pero
    # X-Forwarded-Host=<dominio público>. La firma de Twilio se calculó
    # sobre el dominio público, así que debe validar igual, y el TwiML
    # debe usar el dominio público para el WebSocket, no "localhost".
    public_host = "bj8mz1r7-8000.uks1.devtunnels.ms"
    url = f"https://{public_host}/voice/incoming"
    signature = _twilio_signature(url, {})

    response = client.post(
        "/voice/incoming",
        headers={
            "X-Twilio-Signature": signature,
            "X-Forwarded-Host": public_host,
            "Host": "localhost:8000",
        },
    )

    assert response.status_code == 200
    assert f"wss://{public_host}/media-stream" in response.text
    assert "localhost" not in response.text


def test_voice_incoming_con_firma_valida_devuelve_twiml(client):
    url = "https://testserver/voice/incoming"
    signature = _twilio_signature(url, {})

    response = client.post("/voice/incoming", headers={"X-Twilio-Signature": signature})

    assert response.status_code == 200
    assert "<Stream" in response.text
    assert "wss://testserver/media-stream" in response.text


def test_voice_incoming_con_firma_invalida_devuelve_403(client):
    response = client.post("/voice/incoming", headers={"X-Twilio-Signature": "firma-inventada"})
    assert response.status_code == 403


def test_voice_incoming_sin_firma_devuelve_403(client):
    response = client.post("/voice/incoming")
    assert response.status_code == 403


def test_media_stream_con_firma_invalida_rechaza_la_conexion(client):
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/media-stream", headers={"X-Twilio-Signature": "firma-inventada"}
        ),
    ):
        pass


def test_media_stream_con_firma_valida_acepta_la_conexion(client):
    url = "https://testserver/media-stream"
    signature = _twilio_signature(url, {})

    with client.websocket_connect("/media-stream", headers={"X-Twilio-Signature": signature}) as ws:
        ws.send_json({"event": "start", "start": {"streamSid": "MZtest"}})
        ws.send_json({"event": "stop"})
        # No debe reventar al procesar estos eventos; el intento de conectar
        # con Gemini fallará (dummy-gemini-key no es real) pero eso lo
        # maneja run_with_reconnect, no debe tirar el WebSocket con una
        # excepción sin controlar.


def test_media_stream_acepta_firma_calculada_con_esquema_wss(client):
    # Otra variante vista con tráfico real: puede que Twilio firme el
    # handshake del WebSocket usando "wss://" (el esquema real de la
    # conexión) en vez de "https://".
    url = "wss://testserver/media-stream"
    signature = _twilio_signature(url, {})

    with client.websocket_connect("/media-stream", headers={"X-Twilio-Signature": signature}) as ws:
        ws.send_json({"event": "start", "start": {"streamSid": "MZtest"}})
        ws.send_json({"event": "stop"})


def test_media_stream_cierra_el_websocket_cuando_la_sesion_de_gemini_termina(client, monkeypatch):
    # Reproduce un bug real: si el modelo decide colgar (finalizar_llamada)
    # o el watchdog de inactividad corta la sesión, run_with_reconnect
    # termina por su cuenta, pero antes de este fix el servidor solo salía
    # del bucle al recibir un evento "stop" de Twilio - y Twilio no manda
    # "stop" hasta que la llamada real cuelga. Resultado: el modelo se
    # despedía pero el teléfono se quedaba conectado hasta que el cliente
    # colgaba a mano. El WebSocket debe cerrarse solo en cuanto la sesión
    # de Gemini termina, sin esperar ningún evento del lado de Twilio.
    async def _sesion_termina_al_instante(client, audio_io, tool_router):
        return

    monkeypatch.setattr("pizzeria_bot.server.run_with_reconnect", _sesion_termina_al_instante)

    url = "https://testserver/media-stream"
    signature = _twilio_signature(url, {})

    with (
        client.websocket_connect("/media-stream", headers={"X-Twilio-Signature": signature}) as ws,
        pytest.raises(WebSocketDisconnect),
    ):
        ws.receive_json()


def test_media_stream_con_firma_de_barra_final_tambien_acepta(client):
    # Reproduce un caso real visto con tráfico de Twilio de verdad: para el
    # handshake del WebSocket (a diferencia de un webhook REST normal),
    # Twilio a veces firma sobre la URL con "/" al final aunque la URL real
    # (la del TwiML) no la lleve - la propia documentación de Twilio avisa
    # de esto. Sin aceptar ambas variantes, se rechazan llamadas legítimas.
    url = "https://testserver/media-stream/"  # firma calculada CON barra final
    signature = _twilio_signature(url, {})

    with client.websocket_connect("/media-stream", headers={"X-Twilio-Signature": signature}) as ws:
        ws.send_json({"event": "start", "start": {"streamSid": "MZtest"}})
        ws.send_json({"event": "stop"})
