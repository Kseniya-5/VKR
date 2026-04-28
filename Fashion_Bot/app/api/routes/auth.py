from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.auth import RegisterRequest, LoginRequest
from app.core.security import hash_password, create_access_token, verify_password
from app.db.session import get_db
from app.db.models import User, WebAccount

router = APIRouter(prefix="/auth", tags=["auth"])


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