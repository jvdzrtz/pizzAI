FROM python:3.12-slim

# PortAudio es necesario para compilar/ejecutar pyaudio en Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

# Nota: para audio local (micro/altavoz) dentro de un contenedor hace falta
# reenviar dispositivos de audio del host - no trivial en todos los SO.
# Esta imagen se usa principalmente de cara al futuro despliegue con Twilio,
# donde el audio llega por red (WebSocket) y no por hardware local.
CMD ["pizzeria-bot"]
