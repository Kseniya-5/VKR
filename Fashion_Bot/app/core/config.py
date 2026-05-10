from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    database_url: str
    bot_token: str

    public_base_url: str = "http://127.0.0.1:8080"
    api_base_url: str = "http://fashion-api-service:8000"

    password_pepper: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    cors_origins: list[str] = ["*"]

    media_root: str = "/app/media"
    ml_models_root: str = "/app/ml_models"
    ml_prediction_threshold: float = 0.5
    ml_candidate_photo_limit: int = 30
    ml_auto_tag_candidates_limit: int = 8

    # Vision-advisor поверх CV-модели.
    # Поддерживаем провайдеры:
    #   openwebui  -> локальная llama3.2-vision через Open WebUI /api/chat/completions
    #   openai     -> OpenAI Responses API, если захотите вернуться к нему
    #   disabled   -> только локальный CV fallback
    vision_api_enabled: bool = True
    vision_provider: str = Field(
        default="openwebui",
        validation_alias=AliasChoices("VISION_PROVIDER", "VISION_API_PROVIDER"),
    )

    # Open WebUI / Ollama vision endpoint.
    # Для совместимости поддерживаются и ваши короткие имена API_URL/API_KEY.
    openwebui_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENWEBUI_API_URL", "OLLAMA_VISION_API_URL", "API_URL"),
    )
    openwebui_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENWEBUI_API_KEY", "OLLAMA_VISION_API_KEY", "API_KEY"),
    )
    openwebui_model: str = Field(
        default="llama3.2-vision:latest",
        validation_alias=AliasChoices("OPENWEBUI_MODEL", "OLLAMA_VISION_MODEL", "VISION_MODEL"),
    )

    openwebui_auth_header: str = Field(
        default="Authorization",
        validation_alias=AliasChoices("OPENWEBUI_AUTH_HEADER", "API_AUTH_HEADER"),
    )

    # Старые OpenAI-настройки оставлены как запасной вариант.
    openai_api_key: str | None = None
    openai_vision_model: str = Field(
        default="gpt-5-mini",
        validation_alias=AliasChoices("OPENAI_VISION_MODEL", "OPENAI_MODEL"),
    )

    vision_api_timeout_seconds: int = 120
    vision_image_max_side: int = 1280
    vision_image_jpeg_quality: int = 85

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

BOT_TOKEN = os.getenv("BOT_TOKEN") or settings.bot_token
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")
