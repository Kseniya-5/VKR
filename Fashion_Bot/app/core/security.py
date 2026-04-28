from datetime import datetime, timedelta, timezone
from typing import Any
from jose import jwt
from pwdlib import PasswordHash
from app.core.config import settings

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    peppered_password = f"{password}{settings.password_pepper}"
    return password_hasher.hash(peppered_password)


def verify_password(password: str, password_hash: str) -> bool:
    peppered_password = f"{password}{settings.password_pepper}"
    return password_hasher.verify(peppered_password, password_hash)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )