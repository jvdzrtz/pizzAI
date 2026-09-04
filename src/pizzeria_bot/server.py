"""
Servidor que recibe llamadas telefónicas reales vía Twilio Media Streams
y las conecta con Gemini Live, reutilizando tal cual la misma
PizzeriaCallSession / ToolRouter / dominio que usa la CLI local
(main.py) - cada llamada entrante crea su propio TwilioAudioIO y
ToolRouter, así que cada pedido queda aislado por llamada.

Los dos endpoints (webhook REST y WebSocket) validan la firma
X-Twilio-Signature antes de procesar nada, para que solo Twilio pueda
disparar llamadas reales contra este servidor - sin esto, cualquiera que
encuentre la URL pública (p.ej. tu túnel de ngrok) podría simular
llamadas falsas y gastar cuota de la API de Gemini a tu costa.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import BaseModel
from twilio.request_validator import RequestValidator

from pizzeria_bot.agents.tools import ToolRouter
from pizzeria_bot.audio.twilio_io import TwilioAudioIO
from pizzeria_bot.config import require_gemini_api_key, require_twilio_auth_token, settings
from pizzeria_bot.kitchen.store import store as kitchen_store
from pizzeria_bot.logging_config import setup_logging
from pizzeria_bot.main import run_with_reconnect
from pizzeria_bot.rag.faq_chain import responder_faq

logger = logging.getLogger(__name__)

_KITCHEN_STATIC_DIR = Path(__file__).resolve().parent / "kitchen" / "static"
_KITCHEN_HTML = _KITCHEN_STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    app.state.client = genai.Client(api_key=require_gemini_api_key())
    # Falla al arrancar si no hay Auth Token - sin él no se puede validar
    # ninguna petición, así que el servidor no debe ni empezar a aceptarlas.
    app.state.twilio_validator = RequestValidator(require_twilio_auth_token())
    yield


app = FastAPI(lifespan=lifespan)

# El build de React (front/, ver front/vite.config.ts) escribe aquí:
# index.html se sirve aparte en /kitchen (más abajo, como HTMLResponse
# igual que antes), pero el JS/CSS generado necesita servirse como
# archivos estáticos normales en las rutas que el propio index.html
# referencia (/assets/...).
app.mount("/assets", StaticFiles(directory=_KITCHEN_STATIC_DIR / "assets"), name="kitchen-assets")


def _public_host(headers: Mapping[str, str]) -> str:
    """Host público tal y como lo vio Twilio. Túneles como devtunnel (y a
    veces ngrok) reescriben la cabecera Host a algo interno (ej.
    "localhost:8000") antes de que la petición llegue aquí, pero sí
    reenvían el host real en X-Forwarded-Host - de ahí que no baste con
    mirar Host a secas, o la firma nunca cuadra con la que calculó Twilio
    y el WebSocket del TwiML apuntaría a una dirección inalcanzable desde
    fuera de esta máquina."""
    return headers.get("x-forwarded-host") or headers.get("host", "")


def _public_url(headers: Mapping[str, str], path: str) -> str:
    """Reconstruye la URL pública tal y como la vio Twilio para calcular la
    firma. Siempre https: aunque el túnel le entregue la petición a esta
    app como http en local, lo que Twilio realmente llamó (y sobre lo que
    firmó) es la URL https pública."""
    return f"https://{_public_host(headers)}{path}"


@app.post("/voice/incoming")
async def voice_incoming(request: Request) -> Response:
    """Twilio llama a esto en cuanto entra una llamada. Le decimos que
    abra un Media Stream hacia nuestro WebSocket - el host se toma de la
    propia petición (p.ej. tu túnel de ngrok), no hace falta hardcodearlo."""
    validator: RequestValidator = request.app.state.twilio_validator
    form = await request.form()
    signature = request.headers.get("x-twilio-signature", "")
    url = _public_url(request.headers, request.url.path)

    if not validator.validate(url, dict(form), signature):
        logger.warning(
            "POST /voice/incoming con firma de Twilio inválida - rechazada. "
            "url_reconstruida=%s host_header=%s x-forwarded-host=%s x-forwarded-proto=%s "
            "signature_recibida=%s params=%s",
            url,
            request.headers.get("host"),
            request.headers.get("x-forwarded-host"),
            request.headers.get("x-forwarded-proto"),
            signature,
            dict(form),
        )
        return Response(status_code=403)

    host = _public_host(request.headers)
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Connect>"
        f'<Stream url="wss://{host}/media-stream" />'
        "</Connect>"
        "</Response>"
    )
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    validator: RequestValidator = websocket.app.state.twilio_validator
    signature = websocket.headers.get("x-twilio-signature", "")
    host = _public_host(websocket.headers)
    path = websocket.url.path

    # Para el handshake de un WebSocket, a diferencia de un webhook REST
    # normal, la documentación de Twilio no deja claro con qué esquema
    # (https/wss) ni con qué barra final calcula la firma exactamente -
    # probamos las combinaciones plausibles antes de rechazar, en vez de
    # asumir una y fallar en tráfico real.
    candidates = [
        f"https://{host}{path}",
        f"https://{host}{path}/",
        f"wss://{host}{path}",
        f"wss://{host}{path}/",
    ]
    if not any(validator.validate(candidate, {}, signature) for candidate in candidates):
        # Rechazar ANTES de accept(): no hay nada que aceptar si la firma
        # no es de Twilio.
        logger.warning(
            "WebSocket /media-stream con firma de Twilio inválida - rechazada. "
            "candidatos_probados=%s host_header=%s x-forwarded-host=%s x-forwarded-proto=%s "
            "signature_recibida=%s",
            candidates,
            websocket.headers.get("host"),
            websocket.headers.get("x-forwarded-host"),
            websocket.headers.get("x-forwarded-proto"),
            signature,
        )
        await websocket.close(code=1008)
        return

    await websocket.accept()

    client: genai.Client = websocket.app.state.client
    audio_io = TwilioAudioIO(websocket)
    tool_router = ToolRouter()

    call_task = asyncio.create_task(run_with_reconnect(client, audio_io, tool_router))

    try:
        while True:
            # No basta con esperar solo a websocket.receive_text(): cuando el
            # modelo decide colgar (finalizar_llamada) o el watchdog de
            # inactividad corta la sesión, run_with_reconnect termina por su
            # cuenta pero Twilio no se entera de nada - sigue mandando audio
            # y la llamada real se queda "colgada" (el modelo dice "hasta
            # luego" pero el teléfono sigue sonando) hasta que el propio
            # cliente cuelga a mano. Hay que vigilar call_task también, y en
            # cuanto termine, cerrar nosotros el WebSocket: con
            # <Connect><Stream> y nada después en el TwiML, cerrar el socket
            # es justo la señal que hace que Twilio finalice la llamada.
            receive_task = asyncio.create_task(websocket.receive_text())
            done, _pending = await asyncio.wait(
                {receive_task, call_task}, return_when=asyncio.FIRST_COMPLETED
            )

            if call_task in done:
                receive_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await receive_task
                logger.info(
                    "La sesión con Gemini ha terminado; cerrando el WebSocket para colgar "
                    "la llamada en Twilio."
                )
                break

            raw = receive_task.result()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "start":
                stream_sid = msg["start"]["streamSid"]
                audio_io.set_stream_sid(stream_sid)
                logger.info("Twilio media stream iniciado: %s", stream_sid)
            elif event == "media":
                await audio_io.push_inbound_mulaw(msg["media"]["payload"])
            elif event == "stop":
                logger.info("Twilio media stream detenido (evento 'stop').")
                break
    except WebSocketDisconnect:
        logger.info("WebSocket de Twilio desconectado.")
    finally:
        # La llamada de Gemini no termina sola solo porque Twilio cerró el
        # canal de audio - hay que cancelarla explícitamente. Si ya había
        # terminado por su cuenta (colgado por el modelo o por inactividad)
        # esto no hace nada, es un no-op seguro.
        call_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await call_task
        with contextlib.suppress(Exception):
            await websocket.close()


@app.get("/kitchen")
async def kitchen_page() -> HTMLResponse:
    """Pantalla de cocina: un ticket aparece aquí en cuanto se confirma un
    pedido (ver kitchen/store.py y agents/tools.py: _confirmar_pedido).

    A propósito SIN validación de firma de Twilio - este endpoint no lo
    llama Twilio, lo abre el propio pizzero en un navegador/tablet. Nota
    de seguridad real: no tiene ninguna autenticación tampoco, así que si
    el servidor está expuesto por un túnel público, cualquiera con la URL
    puede ver los pedidos confirmados (nombre, dirección, teléfono). Vale
    para desarrollo/demo; en un despliegue real haría falta protegerlo
    (red privada, o un token compartido)."""
    return HTMLResponse(_KITCHEN_HTML.read_text(encoding="utf-8"))


@app.websocket("/kitchen/ws")
async def kitchen_ws(websocket: WebSocket) -> None:
    """Canal en vivo para la pantalla de cocina: al conectar manda el
    snapshot de tickets ya confirmados, y luego cada ticket nuevo en
    cuanto se confirma un pedido. Puede haber varias pantallas conectadas
    a la vez (kitchen_store.registrar_cliente admite varios clientes)."""
    await websocket.accept()
    kitchen_store.registrar_cliente(websocket)
    try:
        await websocket.send_json(
            {
                "event": "snapshot",
                "tickets": [t.model_dump(mode="json") for t in kitchen_store.snapshot()],
            }
        )
        while True:
            # No esperamos nada del cliente - esto solo mantiene la
            # conexión abierta para poder detectar cuando se cierra.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        kitchen_store.desregistrar_cliente(websocket)


class PreguntaFAQ(BaseModel):
    pregunta: str


class RespuestaFAQ(BaseModel):
    respuesta: str


@app.post("/faq/preguntar")
def faq_preguntar(cuerpo: PreguntaFAQ) -> RespuestaFAQ:
    """Chatbot de políticas/FAQ del restaurante (rag/) para la pantalla de
    cocina - horarios, métodos de pago, zona de reparto, normas. Igual que
    /kitchen, sin firma de Twilio: es una herramienta interna, no algo que
    llame Twilio.

    Función SÍNCRONA a propósito: responder_faq() hace llamadas de red que
    bloquean (embeddings + LLM de Gemini) - al declarar el endpoint como
    `def` normal (no `async def`), FastAPI la ejecuta en su threadpool en
    vez de en el event loop, así una pregunta lenta no bloquea las
    llamadas de voz ni la pantalla de cocina mientras se responde."""
    pregunta = cuerpo.pregunta.strip()
    if not pregunta:
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    try:
        respuesta = responder_faq(pregunta)
    except Exception:
        logger.exception("Error respondiendo pregunta de FAQ: %r", pregunta)
        raise HTTPException(
            status_code=502, detail="No se pudo generar una respuesta ahora mismo."
        ) from None

    return RespuestaFAQ(respuesta=respuesta)
