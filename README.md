# pizzAI 🍕📞

Agente de voz en tiempo real que atiende llamadas telefónicas y toma
pedidos de pizza, construido sobre la Live API de Gemini con function
calling.

## Qué hace la conversación

1. Saluda sin esperar a que el cliente hable primero.
2. Toma pizzas (nombre + tamaño, con `consultar_menu` si preguntan precios
   o ingredientes). Se pueden pedir varias unidades de golpe, quitar un
   ítem ya añadido, o cambiar pizza/tamaño/cantidad sin tener que quitar
   y volver a añadir.
3. Pregunta si es para **recoger en el local** o **a domicilio**:
   - Siempre pide el **nombre** del cliente.
   - Si es a domicilio, pide además la **dirección** (calle + número).
4. Al final, sea cual sea el tipo de entrega, pide el **teléfono** (9 dígitos).
5. Resume el pedido completo y pregunta **una sola vez** si está todo
   correcto — no repite la pregunta ni vuelve a leer el resumen si el
   cliente ya dijo que sí.
6. Al confirmar, el pedido queda **cerrado**: no se puede añadir, quitar
   ni modificar nada más. Si el cliente pide algo después, se le dice que
   ese pedido ya está cerrado.
7. Tras confirmar, se despide y cuelga la llamada él solo (`finalizar_llamada`).

Robustez de la llamada, no solo del "camino feliz":
- **Silencio antes de confirmar**: a los 20s pregunta si sigue ahí; a los
  45s cuelga si no hay respuesta.
- **Silencio después de confirmar**: no tiene sentido preguntar "¿sigues
  ahí?" si ya no queda nada pendiente — directamente se despide y cuelga
  a los 8s: si ni así reacciona, corta sin más a los 20s.
- **Interrupciones (barge-in)**: si el cliente habla mientras el bot
  todavía está sonando, se corta la respuesta y se escucha lo nuevo.
- **Cortes de red**: si Gemini se desconecta a mitad de llamada, se
  reconecta solo sin perder el pedido en curso (reintentos con backoff).
- **item_id nunca se dice en voz alta**: es un detalle interno para que
  el modelo pueda referirse a un ítem concreto al quitar/modificar algo
  — ni siquiera lo revela si se lo piden directamente.

Todos estos tiempos de silencio son configurables por `.env` (ver
`.env.example`) — bájalos si quieres probarlos sin esperar minutos reales.

## Arquitectura

```
Teléfono real (Twilio) ─┐
                        ├─▶ AudioIO ─▶ PizzeriaCallSession (main.py) ◀───▶ Gemini Live API
Mic / altavoz local    ─┘                                    │
                                                               │ tool_call
                                                               ▼
                                                          ToolRouter (agents/) ─▶ Order (domain/)
```

- **`audio/`** — dos implementaciones de la misma interfaz (`AudioIO` en
  `protocol.py`): `LocalAudioIO` (micro/altavoz) y `TwilioAudioIO` (llamada
  real vía Media Streams, con `codecs.py` convirtiendo el mu-law 8kHz de
  Twilio al PCM16 16/24kHz que espera Gemini). `PizzeriaCallSession` no sabe
  ni le importa cuál de las dos está usando.
- **`main.py`** — `PizzeriaCallSession` mantiene la sesión streaming con
  Gemini Live: reenvía el audio en ambas direcciones y recibe un
  `tool_call` cada vez que el modelo decide actuar sobre el pedido.
- **`agents/`** — `ToolRouter` traduce cada `tool_call` en un método de
  `Order` y devuelve el resultado (o el error de negocio) para que Gemini
  lo lea y siga la conversación.
- **`domain/`** — reglas de negocio del pedido (Pydantic). No sabe nada
  de Gemini, audio, ni telefonía. 100% testeable sin mocks.
- **`server.py`** — solo entra en juego para llamadas reales: FastAPI
  recibe el webhook de Twilio (`POST /voice/incoming`, valida su firma y
  devuelve TwiML) y el Media Stream (`WebSocket /media-stream`); por cada
  llamada crea un `TwilioAudioIO` + `ToolRouter` nuevos, así que cada
  pedido queda aislado. En la CLI local (`main.py: run()`) no participa —
  el audio va directo a `LocalAudioIO`.

Una consecuencia real de este diseño: el mu-law 8kHz de la telefonía corta
todo lo que esté por encima de ~4kHz, así que el modelo entiende peor
nombres/direcciones/teléfonos en una llamada real que en local — por eso
el `SYSTEM_PROMPT` obliga a repetir esos datos en voz alta antes de
guardarlos. Y cuando la sesión de Gemini termina (el modelo cuelga, o el
watchdog de inactividad corta), `server.py` cierra el WebSocket él mismo —
si no, Twilio no tiene forma de saber que debe colgar la llamada real.

## Instalación

### Requisito: PortAudio

`pyaudio` necesita la librería del sistema PortAudio.

**Windows** — no necesitas hacer nada aparte, `pip` te trae un wheel
precompilado con PortAudio ya incluido.

**macOS**
```bash
brew install portaudio
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt-get install portaudio19-dev
```

### Instalar el proyecto

- `audio-windows` (PyAudioWPatch) solo existe en Windows y solo hace falta si
  vas a correr la llamada con micro/altavoz local (`LocalAudioIO`).
- `twilio` (FastAPI, uvicorn, `audioop-lts`) hace falta para el servidor de
  telefonía real (`server.py`). Cross-platform.
- En Linux/macOS, o si solo quieres correr los tests de dominio, basta con `dev`.

Con [`uv`](https://docs.astral.sh/uv/) (recomendado):
```bash
# Windows, para correr el bot con micro/altavoz local:
uv venv
uv pip install -e ".[dev,audio-windows]"

# Servidor de telefonía real con Twilio (cualquier plataforma):
uv venv
uv pip install -e ".[dev,twilio]"

# Solo tests/desarrollo del dominio:
uv venv
uv pip install -e ".[dev]"
```

O con pip a secas:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -e ".[dev,audio-windows]"   # Windows con audio local
pip install -e ".[dev,twilio]"          # servidor Twilio
pip install -e ".[dev]"                 # otras plataformas / solo tests
```

### Configurar

```bash
cp .env.example .env
# edita .env y pon tu GEMINI_API_KEY
```

Si quieres forzar un micro/altavoz concreto (`INPUT_DEVICE_NAME`,
`OUTPUT_DEVICE_NAME` en `.env`), primero mira qué nombre exacto usa tu
sistema:
```bash
python scripts/list_audio_devices.py
```

## Ejecutar

```bash
pizzai
```

(o `python -m pizzeria_bot.main`)

Habla como si llamaras a la pizzería. Corta con `Ctrl+C`.

## Telefonía real (Twilio)

Recibe llamadas de verdad en tu móvil y las conecta con Gemini, sin tocar
nada de `domain/` ni `agents/` — solo cambia de dónde sale/entra el audio
(ver [Arquitectura](#arquitectura)).

**Seguridad:** los dos endpoints (`/voice/incoming` y `/media-stream`)
validan la cabecera `X-Twilio-Signature` antes de procesar nada — sin
esto, cualquiera que encontrara tu URL pública podría simular llamadas
falsas y gastar tu cuota de Gemini. El servidor rechaza con `403`
cualquier petición sin firma válida, y ni siquiera arranca si falta
`TWILIO_AUTH_TOKEN` en `.env` (consola de Twilio → Account → Auth Token).

### 1. Arrancar el servidor

```bash
uv pip install -e ".[dev,twilio]"
uvicorn pizzeria_bot.server:app --host 0.0.0.0 --port 8000
```

### 2. Exponerlo a internet

Twilio necesita una URL pública HTTPS. Con
[devtunnel](https://learn.microsoft.com/azure/developer/dev-tunnels/) (Windows, sin sorpresas de antivirus):

```bash
devtunnel user login          # una vez
devtunnel host -p 8000 --allow-anonymous
```

O con [ngrok](https://ngrok.com/) (cross-platform, cuenta gratuita):

```bash
ngrok config add-authtoken TU_TOKEN_AQUI   # una vez
ngrok http 8000
```

Copia la URL pública que te dé cualquiera de los dos. Problemas de
instalación, versión, antivirus o túneles reescribiendo cabeceras →
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### 3. Configurar el número en Twilio

En la [consola de Twilio](https://console.twilio.com/) → **Phone Numbers
→ Manage → Active numbers** → tu número → **Voice Configuration → A call
comes in** → Webhook: tu URL pública + `/voice/incoming`, método
`HTTP POST` → Guardar.

### 4. Probar

**Llamas tú al número de Twilio** — con cuenta trial, solo desde números
verificados en la consola (normalmente tu propio móvil).

> ⚠️ Si tu número de Twilio no es de tu país, esto puede ser una llamada
> **internacional** para tu operadora — revisa la tarifa antes de llamar.

**O que te llame Twilio a ti** (recomendado, más barato — necesita
`TWILIO_ACCOUNT_SID` y `TWILIO_PHONE_NUMBER` en `.env`):

```bash
pizzai-call +34TU_NUMERO https://tu-url-publica
```

> ⚠️ El coste corre por tu saldo de Twilio, no por tu operadora: unos
> **$0.0486/minuto** a un móvil español
> ([tarifas oficiales](https://www.twilio.com/en-us/voice/pricing/es)).
> Recibir la llamada en tu móvil es gratis. Si Twilio rechaza la llamada
> por permisos internacionales (error 21215), la solución está en
> [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

Verás en los logs del servidor cada llamada entrante con el mismo formato
(`Modelo: ...`, `Usuario: ...`, `tool_call ...`) que en modo local — es
literalmente la misma `PizzeriaCallSession` por debajo.

## Tests

```bash
pytest -v
```

Los tests de `domain/` y `agents/` corren sin necesidad de PortAudio
ni de una API key real — son tests de lógica pura. Los de `audio/codecs.py`
y `audio/twilio_io.py` tampoco necesitan una conexión real a Twilio ni a
Gemini (usan un WebSocket falso en memoria). Los de `server.py` (incluida
la validación de firma) usan `TestClient` de FastAPI y generan firmas
Twilio válidas replicando el algoritmo público (HMAC-SHA1), sin necesitar
una cuenta ni credenciales reales. Los de `outbound_call.py` testean solo
la construcción de parámetros (`build_call_params`) — nunca disparan una
llamada real ni gastan saldo de Twilio.

## Docker

Levanta el servidor de telefonía real (`server.py`), no la CLI local — el
audio de una llamada de verdad llega por WebSocket (Twilio), no por
micro/altavoz, así que no hace falta reenviar hardware al contenedor.

```bash
docker build -t pizzai -f docker/Dockerfile .
docker run --env-file .env -p 8000:8000 pizzai
```

Expón el puerto 8000 con ngrok (`ngrok http 8000`) igual que en local —
ver la sección [Telefonía real (Twilio)](#telefonía-real-twilio).

## Roadmap

- [ ] Persistencia real de pedidos (Postgres) — ahora mismo `confirmar_pedido`
      solo loguea, el pedido se pierde al colgar
- [ ] `language_code` a `es-ES` en vez de `es-US` (main.py) — hoy hardcodeado
- [ ] Forma de pago — no se pregunta ni se guarda
- [ ] Vaciar el pedido entero de golpe ("olvídalo todo") — hoy solo se puede
      quitar ítem a ítem con `quitar_item_pedido`
- [ ] RAG sobre el menú (alérgenos, promociones dinámicas)
- [ ] Orquestación LangGraph para flujos de pedido complejos

## Licencia

Código publicado solo con fines de portfolio. Todos los derechos reservados
— ver [LICENSE](LICENSE). No está autorizado su uso, copia ni modificación
sin permiso expreso del autor.
