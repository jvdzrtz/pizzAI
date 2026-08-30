"""
Configuración centralizada de la app. Lee de variables de entorno / .env.

gemini_api_key es opcional a nivel de Settings a propósito: módulos como
audio/twilio_io.py o audio/codecs.py solo necesitan otros campos (sample
rates) y deben poder importarse - y testearse - sin una API key real. La
validación de que la key existe se hace en require_gemini_api_key(), justo
en el punto donde de verdad hace falta (crear el cliente de Gemini), no
al importar este módulo.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-live-preview"
    log_level: str = "INFO"

    # Solo hace falta para server.py (validar que las peticiones vienen
    # realmente de Twilio, ver TWILIO_AUTH_TOKEN en la consola de Twilio).
    # Opcional aquí por el mismo motivo que gemini_api_key.
    twilio_auth_token: str | None = None

    # Solo hace falta para outbound_call.py (disparar una llamada saliente
    # desde tu número de Twilio hacia un móvil real, en vez de llamar tú -
    # evita tarifas internacionales de tu operadora). account_sid y
    # phone_number están en el dashboard de la consola de Twilio.
    twilio_account_sid: str | None = None
    twilio_phone_number: str | None = None

    # Audio
    send_sample_rate: int = 16000
    receive_sample_rate: int = 24000
    chunk_size: int = 1024
    input_device_index: int | None = None
    output_device_index: int | None = None
    input_device_name: str | None = None
    output_device_name: str | None = None

    # Silencio del cliente: a los idle_checkin_seconds le preguntamos si
    # sigue ahí; a los idle_hangup_seconds colgamos. Bájalos para probar
    # el comportamiento sin esperar minutos.
    idle_checkin_seconds: float = 20.0
    idle_hangup_seconds: float = 45.0

    # Red de seguridad: si el pedido ya está confirmado (no queda nada por
    # hacer) y el cliente se queda callado, no preguntamos "¿sigues ahí?"
    # (no tiene sentido, ya no hay nada pendiente) - directamente le pedimos
    # al modelo que se despida y cuelgue. Si ni con eso reacciona, cortamos
    # sin más como último recurso, mucho antes que el timeout normal.
    idle_post_confirm_nudge_seconds: float = 8.0
    idle_hangup_after_confirm_seconds: float = 20.0

    # Tras despedirse y llamar a finalizar_llamada, esperamos este margen
    # (con el micro aún abierto) antes de colgar de verdad - le da tiempo al
    # cliente a decir su propio "hasta luego" a la vez, sin que el corte le
    # pille a media frase.
    hangup_grace_seconds: float = 3.0


settings = Settings()


def require_gemini_api_key() -> str:
    """Valida que haya API key justo antes de crear el cliente de Gemini.
    Copia .env.example a .env y rellena GEMINI_API_KEY si esto falla."""
    if not settings.gemini_api_key:
        raise RuntimeError("Falta GEMINI_API_KEY. Copia .env.example a .env y rellena tu API key.")
    return settings.gemini_api_key


def require_twilio_auth_token() -> str:
    """Valida que haya Auth Token de Twilio antes de arrancar el servidor -
    sin él no se pueden validar las firmas de las peticiones entrantes, así
    que el servidor no debe ni empezar a aceptar tráfico."""
    if not settings.twilio_auth_token:
        raise RuntimeError(
            "Falta TWILIO_AUTH_TOKEN. Cópialo de la consola de Twilio "
            "(Account → Auth Token) y ponlo en .env."
        )
    return settings.twilio_auth_token


def require_twilio_account_sid() -> str:
    """Valida que haya Account SID antes de usar la API REST de Twilio
    (disparar una llamada saliente) - a diferencia del Auth Token, esto no
    hace falta para el servidor en sí, solo para outbound_call.py."""
    if not settings.twilio_account_sid:
        raise RuntimeError(
            "Falta TWILIO_ACCOUNT_SID. Cópialo del dashboard de la consola "
            "de Twilio y ponlo en .env."
        )
    return settings.twilio_account_sid


def require_twilio_phone_number() -> str:
    """Valida que haya un número de Twilio configurado como origen de la
    llamada saliente."""
    if not settings.twilio_phone_number:
        raise RuntimeError(
            "Falta TWILIO_PHONE_NUMBER. Es el número que compraste en "
            "Twilio (formato +1XXXXXXXXXX), ponlo en .env."
        )
    return settings.twilio_phone_number
