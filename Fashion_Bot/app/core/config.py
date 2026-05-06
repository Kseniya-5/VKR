import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    database_url: str
    bot_token: str

    # Public URL that a real user opens in browser/Telegram, for example Cloudflare URL.
    public_base_url: str = "http://127.0.0.1:8080"

    # Internal API URL for pods inside Kubernetes. Telegram bot and worker should use this,
    # not the public Cloudflare URL.
    api_base_url: str = "http://fashion-api-service:8000"

    password_pepper: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # Optional SMTP settings for password recovery.
    # If SMTP is not configured, the one-time login link is still sent to Telegram
    # for linked accounts and printed to API logs for local debugging.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True

    # For local debug you can keep ["*"]. For Cloudflare preferably use:
    # CORS_ORIGINS='["https://xxxx.trycloudflare.com"]'
    cors_origins: list[str] = ["*"]

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
