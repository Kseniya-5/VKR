from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from fastapi.security import OAuth2PasswordRequestForm

from app.api.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    GenerateTelegramLinkCodeResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    RegisterFromTelegramRequest,
)
from app.db.session import get_db
from app.core.deps import get_current_user
from app.db.models import User, WebAccount, AccountLinkCode, PasswordResetToken, TelegramAccount  
from app.core.security import hash_password, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    # Сценарий "сначала веб"
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
    """
    Сценарий 'сначала ТГ → потом веб без дубликатов'
    """
    
    stmt = select(WebAccount).where(WebAccount.email == payload.email)
    result = await db.execute(stmt)
    existing_by_email: WebAccount | None = result.scalar_one_or_none()

    if existing_by_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        )

    # 2. Проверяем, что у current_user ещё нет web-аккаунта
    stmt = select(WebAccount).where(WebAccount.user_id == current_user.id)
    result = await db.execute(stmt)
    existing_for_user: WebAccount | None = result.scalar_one_or_none()

    if existing_for_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Для этого пользователя уже существует веб-аккаунт",
        )

    # 3. Создаём web-аккаунт, НЕ создавая нового User
    password_hash = hash_password(payload.password)

    web_account = WebAccount(
        user_id=current_user.id,
        email=payload.email,
        password_hash=password_hash,
    )
    db.add(web_account)
    await db.commit()

    return {"message": "Веб-аккаунт успешно создан и привязан к Telegram-пользователю"}


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
    """
    'сначала ТГ → потом веб'
    """
    
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
    # Срок жизни кода 10 минут
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


from hashlib import sha256


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebAccount).where(WebAccount.email == payload.email)
    result = await db.execute(stmt)
    web_account: WebAccount | None = result.scalar_one_or_none()

    if not web_account:
        return {"message": "Если такой email существует, ссылка для сброса пароля отправлена."}

    raw_token = token_urlsafe(32)
    token_hash = sha256(raw_token.encode("utf-8")).hexdigest()

    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

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

    print(f"[PASSWORD RESET] token for {web_account.email}: {raw_token}")

    return {"message": "Если такой email существует, ссылка для сброса пароля отправлена."}


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    from hashlib import sha256

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

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    if row["used_at"] is not None or row["expires_at"] < now:
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

    new_hash = hash_password(payload.new_password)

    web_account.password_hash = new_hash

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