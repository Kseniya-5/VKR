import asyncio
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from hashlib import sha256
from secrets import token_urlsafe

try:
    import aiohttp
except Exception:  # pragma: no cover - optional runtime dependency guard
    aiohttp = None

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    GenerateTelegramLinkCodeResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    RegisterFromTelegramRequest,
)
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import AccountLinkCode, PasswordResetToken, TelegramAccount, User, WebAccount
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LinkExistingWebFromTelegramRequest(BaseModel):
    """Credentials of an already existing web account that should be linked to current Telegram user."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class OneTimeLoginRequest(BaseModel):
    token: str = Field(min_length=10, max_length=256)


def _build_one_time_login_link(raw_token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/login-token?token={raw_token}"


def _normalize_expires_at(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


def _send_email_sync(to_email: str, login_link: str) -> None:
    if not _smtp_configured():
        raise RuntimeError("SMTP is not configured")

    msg = EmailMessage()
    msg["Subject"] = "Fashion Bot: одноразовый вход"
    msg["From"] = settings.smtp_from_email or "Fashion Bot <no-reply@example.local>"
    msg["To"] = to_email
    msg.set_content(
        "Здравствуйте!\n\n"
        "Вы запросили восстановление доступа к Fashion Bot.\n"
        "Откройте одноразовую ссылку для входа:\n"
        f"{login_link}\n\n"
        "Ссылка действует 15 минут и сработает только один раз.\n"
        "Если вы не запрашивали вход, просто проигнорируйте это письмо.\n"
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


async def _send_email_login_link(to_email: str, login_link: str) -> bool:
    if not _smtp_configured():
        return False
    try:
        await asyncio.to_thread(_send_email_sync, to_email, login_link)
        return True
    except Exception as exc:
        print(f"[PASSWORD RECOVERY] email send failed for {to_email}: {exc}")
        return False


async def _send_telegram_login_link(telegram_id: int, login_link: str) -> bool:
    if aiohttp is None:
        print("[PASSWORD RECOVERY] aiohttp is not available, cannot send Telegram message")
        return False

    text_body = (
        "🔐 <b>Одноразовый вход в Fashion Bot</b>\n\n"
        "Вы запросили восстановление доступа к веб-версии.\n"
        "Откройте ссылку ниже, чтобы войти один раз:\n\n"
        f"{login_link}\n\n"
        "Ссылка действует 15 минут и сработает только один раз."
    )
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={
                    "chat_id": telegram_id,
                    "text": text_body,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[PASSWORD RECOVERY] Telegram send failed: status={resp.status} body={body}")
                    return False
                return True
    except Exception as exc:
        print(f"[PASSWORD RECOVERY] Telegram send exception for {telegram_id}: {exc}")
        return False


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebAccount).where(WebAccount.email == payload.email)
    result = await db.execute(stmt)
    existing_account = result.scalar_one_or_none()

    if existing_account:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        )

    password_hash = hash_password(payload.password)

    user = User()
    db.add(user)
    await db.flush()

    web_account = WebAccount(
        user_id=user.id,
        email=payload.email,
        password_hash=password_hash,
    )
    db.add(web_account)

    await db.commit()

    return {"message": "Пользователь успешно зарегистрирован"}


@router.post(
    "/register-from-telegram",
    status_code=status.HTTP_201_CREATED,
    summary="Создать веб-аккаунт для уже существующего пользователя из Telegram",
)
async def register_from_telegram(
    payload: RegisterFromTelegramRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scenario: Telegram first -> create a new web account for the same User."""

    stmt = select(WebAccount).where(WebAccount.email == payload.email)
    result = await db.execute(stmt)
    existing_by_email: WebAccount | None = result.scalar_one_or_none()

    if existing_by_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует. Если это ваш веб-аккаунт, используйте сценарий привязки существующего веб-аккаунта.",
        )

    stmt = select(WebAccount).where(WebAccount.user_id == current_user.id)
    result = await db.execute(stmt)
    existing_for_user: WebAccount | None = result.scalar_one_or_none()

    if existing_for_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Для этого пользователя уже существует веб-аккаунт",
        )

    password_hash = hash_password(payload.password)

    web_account = WebAccount(
        user_id=current_user.id,
        email=payload.email,
        password_hash=password_hash,
    )
    db.add(web_account)
    await db.commit()

    return {"message": "Веб-аккаунт успешно создан и привязан к Telegram-пользователю"}


@router.post(
    "/link-existing-web-from-telegram",
    summary="Привязать текущий Telegram-профиль к уже существующему web-аккаунту",
)
async def link_existing_web_from_telegram(
    payload: LinkExistingWebFromTelegramRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Scenario: user already registered in Telegram and already has a separate web account.

    The user opens a Telegram-generated link, enters email/password of an existing web account,
    and we merge Telegram data into the web account user_id. The web account user becomes canonical.
    Photos uploaded from Telegram are moved to the web user, so both interfaces see one wardrobe.
    """

    tg_result = await db.execute(
        select(TelegramAccount).where(TelegramAccount.user_id == current_user.id)
    )
    telegram_account: TelegramAccount | None = tg_result.scalar_one_or_none()

    if not telegram_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текущий пользователь не связан с Telegram",
        )

    web_result = await db.execute(
        select(WebAccount).where(WebAccount.email == payload.email)
    )
    web_account: WebAccount | None = web_result.scalar_one_or_none()

    if not web_account or not verify_password(payload.password, web_account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль веб-аккаунта",
        )

    telegram_user_id = current_user.id
    web_user_id = web_account.user_id

    if str(telegram_user_id) == str(web_user_id):
        access_token = create_access_token(subject=str(web_user_id))
        return {
            "message": "Telegram и web уже связаны с одним аккаунтом",
            "access_token": access_token,
            "token_type": "bearer",
            "merged": False,
        }

    current_web_result = await db.execute(
        select(WebAccount).where(WebAccount.user_id == telegram_user_id)
    )
    current_web_account = current_web_result.scalar_one_or_none()
    if current_web_account:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Этот Telegram-пользователь уже имеет другой веб-аккаунт. Сначала удалите или отвяжите текущий web-аккаунт.",
        )

    web_tg_result = await db.execute(
        select(TelegramAccount).where(TelegramAccount.user_id == web_user_id)
    )
    existing_web_telegram: TelegramAccount | None = web_tg_result.scalar_one_or_none()
    if existing_web_telegram and existing_web_telegram.telegram_id != telegram_account.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Этот веб-аккаунт уже связан с другим Telegram",
        )

    # Move data created while using Telegram-only account to the existing web account.
    # Keep raw SQL explicit: these tables exist in the current migration and models.
    move_tables = [
        "user_photos",
        "model_tasks",
        "outfits",
        "recommendations",
    ]
    moved: dict[str, int] = {}
    for table_name in move_tables:
        result = await db.execute(
            text(
                f"""
                UPDATE {table_name}
                SET user_id = :web_user_id
                WHERE user_id = :telegram_user_id
                """
            ),
            {
                "web_user_id": str(web_user_id),
                "telegram_user_id": str(telegram_user_id),
            },
        )
        moved[table_name] = result.rowcount or 0

    await db.execute(
        text(
            """
            UPDATE telegram_accounts
            SET user_id = :web_user_id
            WHERE telegram_id = :telegram_id
            """
        ),
        {
            "web_user_id": str(web_user_id),
            "telegram_id": telegram_account.telegram_id,
        },
    )

    await db.execute(
        text(
            """
            DELETE FROM account_link_codes
            WHERE user_id IN (:telegram_user_id, :web_user_id)
            """
        ),
        {
            "telegram_user_id": str(telegram_user_id),
            "web_user_id": str(web_user_id),
        },
    )

    await db.execute(
        text(
            """
            UPDATE users
            SET is_deleted = TRUE,
                deleted_at = :deleted_at,
                updated_at = :deleted_at
            WHERE id = :telegram_user_id
            """
        ),
        {
            "telegram_user_id": str(telegram_user_id),
            "deleted_at": datetime.now(timezone.utc),
        },
    )

    await db.commit()

    access_token = create_access_token(subject=str(web_user_id))
    return {
        "message": "Telegram успешно связан с существующим веб-аккаунтом",
        "access_token": access_token,
        "token_type": "bearer",
        "merged": True,
        "moved": moved,
    }


@router.post("/login")
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebAccount).where(WebAccount.email == payload.email)
    result = await db.execute(stmt)
    web_account: WebAccount | None = result.scalar_one_or_none()

    if not web_account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )

    if not verify_password(payload.password, web_account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )

    access_token = create_access_token(subject=str(web_account.user_id))

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/dev-token-for-telegram")
async def dev_token_for_telegram(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Temporary access token for a Telegram user already registered in telegram_accounts."""

    result = await db.execute(
        text(
            """
            SELECT user_id
            FROM telegram_accounts
            WHERE telegram_id = :telegram_id
            LIMIT 1
            """
        ),
        {"telegram_id": telegram_id},
    )
    user_id = result.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram user not registered",
        )

    access_token = create_access_token(subject=str(user_id))
    return {"access_token": access_token, "token_type": "bearer"}


@router.post(
    "/link/telegram/code",
    response_model=GenerateTelegramLinkCodeResponse,
    summary="Сгенерировать одноразовый код для привязки Telegram",
)
async def generate_telegram_link_code(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    await db.execute(
        text(
            """
            DELETE FROM account_link_codes
            WHERE user_id = :user_id
            """
        ),
        {"user_id": str(current_user.id)},
    )

    raw_code = token_urlsafe(6).upper().replace("=", "").replace("-", "")
    code = raw_code[:8]

    link_code = AccountLinkCode(
        code=code,
        user_id=current_user.id,
        expires_at=expires_at,
    )
    db.add(link_code)
    await db.commit()

    return GenerateTelegramLinkCodeResponse(
        code=code,
        expires_at=expires_at.isoformat(),
    )


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Sends a one-time login link for password recovery.

    Delivery priority:
    1. Telegram, if this web account is linked to Telegram.
    2. Email, if SMTP settings are configured.
    3. API logs for local development/debugging.

    The response is intentionally generic and never reveals whether the email exists.
    """
    stmt = select(WebAccount).where(WebAccount.email == payload.email)
    result = await db.execute(stmt)
    web_account: WebAccount | None = result.scalar_one_or_none()

    generic_response = {
        "message": "Если такой email существует, одноразовая ссылка для входа отправлена в Telegram или на email."
    }

    if not web_account:
        return generic_response

    raw_token = token_urlsafe(32)
    token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    login_link = _build_one_time_login_link(raw_token)

    await db.execute(
        text(
            """
            DELETE FROM password_reset_tokens
            WHERE user_id = :user_id
            """
        ),
        {"user_id": str(web_account.user_id)},
    )

    reset_token = PasswordResetToken(
        user_id=web_account.user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(reset_token)
    await db.commit()

    delivered = False

    tg_result = await db.execute(
        text(
            """
            SELECT telegram_id
            FROM telegram_accounts
            WHERE user_id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": str(web_account.user_id)},
    )
    telegram_id = tg_result.scalar_one_or_none()

    if telegram_id:
        delivered = await _send_telegram_login_link(int(telegram_id), login_link) or delivered

    delivered = await _send_email_login_link(web_account.email, login_link) or delivered

    if not delivered:
        print(
            "[ONE-TIME LOGIN] SMTP is not configured or delivery failed. "
            f"Link for {web_account.email}: {login_link}"
        )

    return generic_response


@router.post("/login-with-reset-token")
async def login_with_reset_token(
    payload: OneTimeLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    token_hash = sha256(payload.token.strip().encode("utf-8")).hexdigest()

    result = await db.execute(
        text(
            """
            SELECT id, user_id, expires_at, used_at
            FROM password_reset_tokens
            WHERE token_hash = :token_hash
            LIMIT 1
            """
        ),
        {"token_hash": token_hash},
    )
    row = result.mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверная или просроченная одноразовая ссылка",
        )

    now = datetime.now(timezone.utc)
    expires_at = _normalize_expires_at(row["expires_at"])
    if row["used_at"] is not None or expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверная или просроченная одноразовая ссылка",
        )

    user_id = row["user_id"]
    web_result = await db.execute(
        select(WebAccount).where(WebAccount.user_id == user_id)
    )
    web_account: WebAccount | None = web_result.scalar_one_or_none()

    if not web_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Веб-аккаунт не найден",
        )

    await db.execute(
        text(
            """
            UPDATE password_reset_tokens
            SET used_at = :used_at
            WHERE id = :id
            """
        ),
        {"used_at": now, "id": str(row["id"])},
    )
    await db.commit()

    access_token = create_access_token(subject=str(user_id))
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    token_hash = sha256(payload.token.strip().encode("utf-8")).hexdigest()

    result = await db.execute(
        text(
            """
            SELECT id, user_id, expires_at, used_at
            FROM password_reset_tokens
            WHERE token_hash = :token_hash
            LIMIT 1
            """
        ),
        {"token_hash": token_hash},
    )
    row = result.mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный или просроченный токен",
        )

    now = datetime.now(timezone.utc)
    expires_at = _normalize_expires_at(row["expires_at"])
    if row["used_at"] is not None or expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный или просроченный токен",
        )

    user_id = row["user_id"]
    wa_result = await db.execute(
        select(WebAccount).where(WebAccount.user_id == user_id)
    )
    web_account = wa_result.scalar_one_or_none()

    if not web_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный или просроченный токен",
        )

    web_account.password_hash = hash_password(payload.new_password)

    await db.execute(
        text(
            """
            UPDATE password_reset_tokens
            SET used_at = :used_at
            WHERE id = :id
            """
        ),
        {"used_at": now, "id": str(row["id"])},
    )

    await db.commit()

    return {"message": "Пароль успешно обновлён"}


@router.post("/token")
async def login_for_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    email = form_data.username.strip().lower()

    stmt = select(WebAccount).where(WebAccount.email == email)
    result = await db.execute(stmt)
    web_account: WebAccount | None = result.scalar_one_or_none()

    if not web_account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, web_account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(web_account.user_id))

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
