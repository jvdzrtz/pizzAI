"""
Configuración centralizada de la app. Lee de variables de entorno / .env
y valida que todo lo necesario esté presente antes de arrancar nada.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str
    gemini_model: str = "gemini-3.1-flash-live-preview"
    log_level: str = "INFO"

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


settings = Settings()
