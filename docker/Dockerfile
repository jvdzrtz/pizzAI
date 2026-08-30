FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[twilio]"

# Esta imagen levanta el servidor de telefonía real (server.py), no la CLI
# local: el audio de una llamada de verdad llega por WebSocket (Twilio Media
# Streams), no por micro/altavoz local - eso no se puede reenviar a un
# contenedor de forma trivial. Para la CLI local usa `pizzai` fuera de Docker.
EXPOSE 8000
CMD ["uvicorn", "pizzeria_bot.server:app", "--host", "0.0.0.0", "--port", "8000"]
