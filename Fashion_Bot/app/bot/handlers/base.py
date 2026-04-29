from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings


router = Router()

engine = create_async_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    async with SessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT 1
                FROM telegram_accounts
                WHERE telegram_id = :telegram_id
                LIMIT 1
                """
            ),
            {"telegram_id": telegram_id},
        )
        tg_account_exists = result.scalar_one_or_none()

        if tg_account_exists is not None:
            await message.answer(
                "Привет! Ваш Telegram уже привязан к аккаунту."
            )
            return

        user_result = await session.execute(
            text(
                """
                INSERT INTO users DEFAULT VALUES
                RETURNING id
                """
            )
        )
        user_id = user_result.scalar_one()

        await session.execute(
            text(
                """
                INSERT INTO telegram_accounts (
                    telegram_id,
                    user_id,
                    username,
                    first_name,
                    last_name
                )
                VALUES (
                    :telegram_id,
                    :user_id,
                    :username,
                    :first_name,
                    :last_name
                )
                """
            ),
            {
                "telegram_id": telegram_id,
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
            },
        )

        await session.commit()

    await message.answer(
        "Привет! Telegram сохранён. Для привязки аккаунта используйте команду /profile."
    )