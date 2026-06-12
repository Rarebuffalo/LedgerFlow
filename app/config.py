import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/ledgerflow"
    REDIS_URL: str = "redis://redis:6379/0"
    GEMINI_API_KEY: str = ""
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10MB

    # To read from .env if present
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Create upload dir locally if it doesn't exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
