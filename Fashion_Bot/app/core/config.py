import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    database_url: str
    bot_token: str
    public_base_url: str = "http://127.0.0.1"

    password_pepper: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
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