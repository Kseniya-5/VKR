import re
from pydantic import BaseModel, EmailStr, Field, field_validator

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        password = value.strip()

        if len(password) < PASSWORD_MIN_LENGTH:
            raise ValueError("Пароль слишком короткий")

        if len(password) > PASSWORD_MAX_LENGTH:
            raise ValueError("Пароль слишком длинный")

        if not re.search(r"[A-Za-zА-Яа-я]", password):
            raise ValueError("Пароль должен содержать хотя бы одну букву")

        if not re.search(r"\d", password):
            raise ValueError("Пароль должен содержать хотя бы одну цифру")

        return password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()