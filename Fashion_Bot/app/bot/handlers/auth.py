from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.services.user_deletion import enqueue_cleanup_user_data


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


@router.message(Command("profile"))
async def profile_cmd(message: Message):
    telegram_id = message.from_user.id

    async with SessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    ta.telegram_id,
                    ta.username,
                    ta.first_name,
                    ta.last_name,
                    ta.user_id,
                    wa.email
                FROM telegram_accounts ta
                JOIN users u ON u.id = ta.user_id
                LEFT JOIN web_accounts wa ON wa.user_id = u.id
                WHERE ta.telegram_id = :telegram_id
                LIMIT 1
                """
            ),
            {"telegram_id": telegram_id},
        )
        row = result.mappings().first()

    if not row:
        await message.answer(
            "Telegram ещё не привязан. Сначала отправьте /start."
        )
        return

    email = row["email"] or "не привязан"
    username = row["username"] or "не указан"
    first_name = row["first_name"] or "не указано"
    last_name = row["last_name"] or "не указано"

    await message.answer(
        "Ваш профиль:\n"
        f"user_id: {row['user_id']}\n"
        f"telegram_id: {row['telegram_id']}\n"
        f"username: {username}\n"
        f"first_name: {first_name}\n"
        f"last_name: {last_name}\n"
        f"email: {email}"
    )


@router.message(Command("unlink_tg"))
async def unlink_tg_cmd(message: Message):
    telegram_id = message.from_user.id

    async with SessionLocal() as session:
        result = await session.execute(
            text(
                """
                DELETE FROM telegram_accounts
                WHERE telegram_id = :telegram_id
                RETURNING telegram_id
                """
            ),
            {"telegram_id": telegram_id},
        )
        deleted = result.scalar_one_or_none()

        await session.commit()

    if deleted is None:
        await message.answer("Привязка Telegram не найдена.")
        return

    await message.answer("Telegram успешно отвязан от аккаунта.")


@router.message(Command("delete_me"))
async def delete_me_cmd(message: Message):
    telegram_id = message.from_user.id

    async with SessionLocal() as session:
        result = await session.execute(
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

    if user_id is None:
        await message.answer(
            "Пользователь не найден. Сначала выполните /start."
        )
        return

    task = enqueue_cleanup_user_data(str(user_id))

    await message.answer(
        "Удаление поставлено в очередь.\n"
        f"Celery task_id: {task.id}"
    )