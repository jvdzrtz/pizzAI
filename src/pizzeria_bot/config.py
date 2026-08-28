"""
Configuración centralizada de la app. Lee de variables de entorno / .env
y valida que todo lo necesario esté presente antes de arrancar nada.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str
    gemini_model: str = "gemini-3.1-flash-live-preview"

    # Audio
    send_sample_rate: int = 16000
    receive_sample_rate: int = 24000
    chunk_size: int = 1024
    input_device_index: int | None = None
    output_device_index: int | None = None
    input_device_name: str | None = None
    output_device_name: str | None = None


settings = Settings()
