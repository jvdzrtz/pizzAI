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
┌─────────────────┐     audio (mic/altavoz)     ┌──────────────────┐
│   LocalAudioIO   │ ◄─────────────────────────► │  PizzeriaCall    │
│  (audio/)        │                              │  Session (main.py)│
└─────────────────┘                              └────────┬─────────┘
                                                            │ tool_call
                                                   ┌────────▼─────────┐
                                                   │   ToolRouter      │
                                                   │   (agents/)       │
                                                   └────────┬─────────┘
                                                            │
                                                   ┌────────▼─────────┐
                                                   │      Order        │
                                                   │   (domain/)        │
                                                   └───────────────────┘
```

- **`domain/`** — reglas de negocio del pedido (Pydantic). No sabe nada
  de Gemini, audio, ni telefonía. 100% testeable sin mocks.
- **`agents/`** — tools y prompt del agente de voz. Traduce entre el
  esquema que entiende Gemini y el dominio.
- **`audio/`** — entrada/salida de audio, intercambiable (`AudioIO`
  en `protocol.py`): `LocalAudioIO` (micro/altavoz local) y
  `TwilioAudioIO` (llamada telefónica real vía Media Streams,
  con `codecs.py` para la conversión mu-law↔PCM y el resampling
  8kHz↔16/24kHz) implementan la misma interfaz — `PizzeriaCallSession`
  no sabe ni le importa cuál de las dos está usando.
- **`main.py`** — `PizzeriaCallSession` orquesta una llamada: conecta la
  sesión de Gemini Live, reenvía audio, y ejecuta tool calls con
  reconexión automática. `run()` es el punto de entrada de la CLI local.
- **`server.py`** — servidor FastAPI para llamadas reales: recibe el
  webhook de Twilio (`POST /voice/incoming`) y el Media Stream
  (`WebSocket /media-stream`). Cada llamada entrante crea su propio
  `TwilioAudioIO` + `ToolRouter` y reutiliza la misma
  `run_with_reconnect` que la CLI — un pedido por llamada, aislado.

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
nada de `domain/` ni `agents/` — solo cambia de dónde sale/entra el audio.

### 0. Seguridad: validar que las peticiones vienen de Twilio

Los dos endpoints (`/voice/incoming` y `/media-stream`) comprueban la
cabecera `X-Twilio-Signature` en cada petición — sin esto, cualquiera que
encontrara tu URL pública de ngrok podría simular llamadas falsas y gastar
tu cuota de la API de Gemini. Necesitas tu **Twilio Auth Token** (consola
de Twilio → Account → Auth Token) en `.env`:

```bash
TWILIO_AUTH_TOKEN=tu_auth_token_aqui
```

El servidor rechaza con `403` cualquier petición sin firma válida, y ni
siquiera arranca si falta el Auth Token en `.env`.

> ⚠️ **Con devtunnel** (y a veces con ngrok): el túnel puede reescribir la
> cabecera `Host` que le llega a tu app a algo interno (`localhost:8000`)
> en vez del dominio público real, aunque sí reenvía el dominio público en
> `X-Forwarded-Host`. Si ves `403` rechazando peticiones que sabes que son
> de Twilio de verdad (IP de Twilio en el log), es esto — el servidor ya
> usa `X-Forwarded-Host` cuando está presente (`server.py: _public_host`),
> pero si algún día cambias de túnel y vuelve a fallar, es lo primero que
> hay que revisar (los logs de `403` en `voice_incoming`/`media_stream`
> imprimen `host_header` y `x-forwarded-host` para diagnosticarlo).
>
> Además, para el **handshake del WebSocket** específicamente (no para el
> webhook POST), Twilio a veces firma la URL con una barra final `/` aunque
> la URL real (la del TwiML) no la lleve — es una inconsistencia conocida
> y documentada por el propio Twilio, no un bug nuestro. `media_stream`
> ya prueba la firma con y sin barra final antes de rechazar.

### 1. Arrancar el servidor

```bash
uv pip install -e ".[dev,twilio]"
uvicorn pizzeria_bot.server:app --host 0.0.0.0 --port 8000
```

### 2. Exponerlo a internet

Twilio necesita una URL pública (HTTPS) para llamar a tu servidor local.
Esto es una herramienta de sistema, fuera del proyecto — no toca
`pyproject.toml` ni el venv. Dos opciones:

#### Opción A: devtunnel (Microsoft, recomendado en Windows)

Binario firmado por Microsoft — sin sorpresas con el antivirus.

```powershell
winget install Microsoft.devtunnel
```
> Tras instalar, **reinicia VS Code entero** (no solo la pestaña de
> terminal) — el PATH nuevo lo recoge un proceso de VS Code recién
> arrancado, no una terminal nueva dentro del mismo VS Code ya abierto.
> Mientras tanto, usa la ruta completa: busca `devtunnel.exe` dentro de
> `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Microsoft.devtunnel_...`.

```bash
devtunnel user login          # una vez, abre el navegador para iniciar sesión
```

**Importante**: `devtunnel host -p 8000 --allow-anonymous` (sin más) crea un
túnel nuevo con URL aleatoria **cada vez que lo arrancas** — significa
volver a actualizar el webhook en Twilio cada sesión. Para evitarlo, crea un
túnel con nombre fijo **una sola vez**:

```bash
devtunnel create pizzai --allow-anonymous
devtunnel port create pizzai -p 8000
```

Y a partir de ahí, arráncalo siempre así (misma URL pública todas las
veces, no hace falta tocar Twilio de nuevo):

```bash
devtunnel host pizzai
```

Te da una URL pública fija tipo `https://xxxxx-8000.<region>.devtunnels.ms`
(el `xxxxx` es un identificador aparte del nombre del túnel, pero se
mantiene estable mientras reutilices `devtunnel host pizzai`).

#### Opción B: ngrok

```powershell
winget install ngrok.ngrok
```
> Mismo aviso de reiniciar VS Code entero que con devtunnel.
>
> **Ojo**: el paquete de winget puede instalar una versión antigua
> (nos pasó: 3.3.1, insuficiente — ngrok pide ≥3.20.0). Actualízala con
> `ngrok update`. Y el propio actualizador de ngrok puede activar un
> falso positivo del antivirus (`Trojan:...!rfn`, detección heurística
> por reputación, no una firma real) al reemplazar su propio `.exe` — si
> te pasa, es tu decisión restaurarlo desde Windows Security o cambiar a
> la opción A.

Crea cuenta gratis en [dashboard.ngrok.com/signup](https://dashboard.ngrok.com/signup),
copia tu token de [dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken):
```bash
ngrok config add-authtoken TU_TOKEN_AQUI   # una vez, antes de poder usar "ngrok http"
ngrok http 8000
```

Sea cual sea la opción, copia la URL pública que te dé — cambia en cada
ejecución si usas el plan gratuito, así que repite este paso cada vez que
reinicies el túnel.

### 3. Configurar el número en Twilio

En la [consola de Twilio](https://console.twilio.com/):

1. **Phone Numbers → Manage → Active numbers** → tu número de prueba.
2. En **Voice Configuration → A call comes in**, selecciona "Webhook" y
   pon tu URL pública + `/voice/incoming` (ej.
   `https://xxxx-xxxx.ngrok-free.app/voice/incoming` o
   `https://xxxxx-8000.<region>.devtunnels.ms/voice/incoming`), método `HTTP POST`.
3. Guarda.

### 4. Probar

**Opción A — llamas tú al número de Twilio.** Con una cuenta **trial**, solo
puedes llamar desde números verificados en la consola de Twilio (normalmente
tu propio móvil) — es configuración de la cuenta, no hay nada que tocar en
el código para eso.

> ⚠️ Si tu número de Twilio no es del mismo país que tu móvil, esto puede
> ser una llamada **internacional** para tu operadora — revisa la tarifa
> antes de llamar. Con un operador español normal, llamar a un número de
> EE.UU. puede costar varios euros por minuto (no es un coste de Twilio,
> es de tu propia operadora).

**Opción B — que te llame Twilio a ti (recomendado, más barato).** En vez de
marcar tú, dispara la llamada con `pizzai-call`:

```bash
pizzai-call +34TU_NUMERO https://xxxxx-8000.<region>.devtunnels.ms
```

Necesitas `TWILIO_ACCOUNT_SID` y `TWILIO_PHONE_NUMBER` en `.env` (ver
`.env.example`). El coste corre por tu saldo de Twilio, no por tu operadora
— por ejemplo, llamar a un móvil español cuesta unos **$0.0486/minuto**
([tarifas oficiales de Twilio](https://www.twilio.com/en-us/voice/pricing/es)),
y recibir la llamada en tu móvil es gratis, como cualquier llamada entrante.

> ⚠️ La primera vez, Twilio puede rechazar la llamada con
> `Account not authorized to call +34... - Perhaps you need to enable some
> international permissions` (error 21215). Es un permiso de cuenta, no un
> bug: por defecto las cuentas nuevas no tienen habilitados todos los
> países para llamadas salientes (protección antifraude). Actívalo en
> [Geo Permissions](https://www.twilio.com/console/voice/calls/geo-permissions/low-risk)
> → busca tu país (España está en "Western Europe") → actívalo → guarda.

Con cualquiera de las dos opciones, verás en los logs del servidor cada
llamada entrante, con el mismo formato de log (`Modelo: ...`, `Usuario: ...`,
`tool_call ...`) que en modo local — es literalmente la misma
`PizzeriaCallSession` por debajo.

> Nota técnica: Twilio Media Streams manda audio mu-law mono a 8kHz: el
> `TwilioAudioIO` (`audio/twilio_io.py`) lo convierte a PCM16 16kHz para
> Gemini de entrada, y de PCM16 24kHz a mu-law 8kHz de vuelta para Twilio
> (`audio/codecs.py`, usando `audioop.ratecv` para el resampling — sin
> numpy/scipy).
>
> Esto tiene una consecuencia real: el mu-law 8kHz es el códec clásico de
> telefonía, pensado para voz inteligible, no para claridad — corta todo lo
> que esté por encima de ~4kHz. Es objetivamente peor que el PCM 16kHz sin
> comprimir de unas pruebas locales con micrófono, y hace que el modelo
> entienda peor datos concretos (nombres, direcciones, números de teléfono)
> en una llamada real que en local — no es un problema de latencia/ping,
> es la calidad del audio de la red telefónica en sí, algo inherente a
> cualquier bot de voz sobre PSTN. El `SYSTEM_PROMPT` (`agents/prompts.py`)
> mitiga esto pidiéndole al modelo que repita en voz alta el nombre, la
> dirección y el teléfono (dígito a dígito) nada más recogerlos, para que
> el cliente pueda corregir un error de transcripción antes de que llegue
> al resumen final.

> Nota técnica: cuando el modelo llama a `finalizar_llamada` (o el
> watchdog de inactividad corta la sesión), `run_with_reconnect` termina
> por su cuenta, pero eso no basta para colgar la llamada real — el
> WebSocket de Twilio sigue abierto hasta que alguien lo cierra. El bucle
> de `media_stream` (`server.py`) vigila `call_task` con `asyncio.wait`
> además de los eventos entrantes de Twilio, y en cuanto la sesión de
> Gemini termina, cierra el WebSocket él mismo: con `<Connect><Stream>` y
> nada después en el TwiML, cerrar el socket es la señal que hace que
> Twilio cuelgue la llamada de verdad, en vez de dejarla conectada en
> silencio hasta que el cliente cuelgue a mano.

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
