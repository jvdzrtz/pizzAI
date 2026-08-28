# pizzAI 🍕📞

Agente de voz en tiempo real que atiende llamadas telefónicas y toma
pedidos de pizza, construido sobre la Live API de Gemini con function
calling.

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
- **`audio/`** — entrada/salida de audio. Hoy es micro/altavoz local
  (`LocalAudioIO`); el roadmap prevé un `TwilioAudioIO` que recibe el
  audio de una llamada telefónica real en vez de hardware local, sin
  tocar el resto del código.
- **`main.py`** — orquesta todo: conecta la sesión de Gemini Live,
  reenvía audio, y ejecuta tool calls con reconexión automática.

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

`audio-windows` (PyAudioWPatch) solo existe en Windows y solo hace falta si
vas a correr la llamada de verdad en local (`LocalAudioIO`, micro/altavoz).
En Linux/macOS, o si solo quieres correr los tests de dominio, basta con `dev`.

Con [`uv`](https://docs.astral.sh/uv/) (recomendado):
```bash
# Windows, para correr el bot con micro/altavoz local:
uv venv
uv pip install -e ".[dev,audio-windows]"

# Otras plataformas, o solo para tests/desarrollo:
uv venv
uv pip install -e ".[dev]"
```

O con pip a secas:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -e ".[dev,audio-windows]"   # Windows con audio local
pip install -e ".[dev]"                 # otras plataformas / solo tests
```

### Configurar

```bash
cp .env.example .env
# edita .env y pon tu GEMINI_API_KEY
```

## Ejecutar

```bash
pizzai
```

(o `python -m pizzeria_bot.main`)

Habla como si llamaras a la pizzería. Corta con `Ctrl+C`.

## Tests

```bash
pytest -v
```

Los tests de `domain/` y `agents/` corren sin necesidad de PortAudio
ni de una API key real — son tests de lógica pura.

## Docker

```bash
docker build -t pizzai -f docker/Dockerfile .
docker run --env-file .env pizzai
```

> Nota: el audio local (micro/altavoz) no se reenvía fácilmente a un
> contenedor. Esta imagen está pensada de cara a la futura integración
> con Twilio, donde el audio llega por WebSocket y no por hardware.

## Roadmap

- [ ] Sustituir `LocalAudioIO` por `TwilioAudioIO` (Media Streams)
- [ ] Persistencia real de pedidos (Postgres)
- [ ] RAG sobre el menú (alérgenos, promociones dinámicas)
- [ ] Orquestación LangGraph para flujos de pedido complejos

## Licencia

Código publicado solo con fines de portfolio. Todos los derechos reservados
— ver [LICENSE](LICENSE). No está autorizado su uso, copia ni modificación
sin permiso expreso del autor.
