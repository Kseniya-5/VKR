from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.bot.keyboards import (
    start_keyboard,
    account_management_keyboard,
    confirm_action_keyboard,
)


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


async def get_user_id_by_telegram(telegram_id: int):
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
        return result.scalar_one_or_none()


async def is_registered(telegram_id: int) -> bool:
    user_id = await get_user_id_by_telegram(telegram_id)
    return user_id is not None


@router.message(Command("unlink_tg"))
async def unlink_tg_cmd(message: Message):
    if not await is_registered(message.from_user.id):
        await message.answer(
            "Привязка Telegram не найдена.",
            reply_markup=start_keyboard(is_registered=False),
        )
        return

    await message.answer(
        "⚙️ <b>Управление аккаунтом</b>\n\n"
        "Здесь вы можете:\n"
        "• <b>🔌 Отвязать Telegram</b> — бот перестанет быть связан с аккаунтом, "
        "но сам аккаунт в сервисе сохранится.\n"
        "• <b>🗑 Удалить аккаунт</b> — аккаунт и связанные данные сервиса будут удалены.\n\n"
        "⚠️ После выполнения действия текущее меню будет удалено.\n\n"
        "Выберите нужное действие:",
        parse_mode="HTML",
        reply_markup=account_management_keyboard(),
    )


@router.message(Command("delete_me"))
async def delete_me_cmd(message: Message):
    if not await is_registered(message.from_user.id):
        await message.answer(
            "Пользователь не найден. Сначала зарегистрируйтесь.",
            reply_markup=start_keyboard(is_registered=False),
        )
        return

    await message.answer(
        "⚠️ <b>Подтверждение удаления аккаунта</b>\n\n"
        "После удаления аккаунта будут удалены ваши данные в сервисе.\n"
        "Также текущее меню будет очищено.\n\n"
        "Точно продолжить?",
        parse_mode="HTML",
        reply_markup=confirm_action_keyboard("delete_me"),
    )


@router.callback_query(F.data == "account_management")
async def account_management_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id

    if not await is_registered(telegram_id):
        await callback.message.edit_text(
            "Сначала зарегистрируйтесь.",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "⚙️ <b>Управление аккаунтом</b>\n\n"
        "Здесь вы можете:\n"
        "• <b>🔌 Отвязать Telegram</b> — бот перестанет быть связан с аккаунтом, "
        "но сам аккаунт в сервисе сохранится.\n"
        "• <b>🗑 Удалить аккаунт</b> — аккаунт и связанные данные сервиса будут удалены.\n\n"
        "⚠️ После отвязки или удаления текущее меню будет очищено.\n\n"
        "Выберите нужное действие:",
        parse_mode="HTML",
        reply_markup=account_management_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "unlink_tg")
async def unlink_tg_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id

    if not await is_registered(telegram_id):
        await callback.message.edit_text(
            "Привязка Telegram не найдена.",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "⚠️ <b>Подтверждение отвязки Telegram</b>\n\n"
        "После отвязки бот больше не будет связан с вашим аккаунтом.\n"
        "Сам аккаунт в сервисе сохранится.\n"
        "Текущее меню будет удалено.\n\n"
        "Вы точно хотите отвязать Telegram?",
        parse_mode="HTML",
        reply_markup=confirm_action_keyboard("unlink_tg"),
    )
    await callback.answer()


@router.callback_query(F.data == "delete_me")
async def delete_me_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id

    if not await is_registered(telegram_id):
        await callback.message.edit_text(
            "Пользователь не найден. Сначала зарегистрируйтесь.",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "⚠️ <b>Подтверждение удаления аккаунта</b>\n\n"
        "После удаления аккаунта будут удалены ваши данные в сервисе.\n"
        "Текущее меню будет удалено.\n\n"
        "Вы точно хотите удалить аккаунт?",
        parse_mode="HTML",
        reply_markup=confirm_action_keyboard("delete_me"),
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_unlink_tg")
async def confirm_unlink_tg_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id

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

    try:
        await callback.message.delete()
    except Exception:
        pass

    if deleted is None:
        await callback.message.answer(
            "Привязка Telegram не найдена.",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.answer(
        "✅ Telegram успешно отвязан от аккаунта.\n"
        "Чтобы снова пользоваться ботом, зарегистрируйтесь заново.",
        reply_markup=start_keyboard(is_registered=False),
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_delete_me")
async def confirm_delete_me_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    user_id = await get_user_id_by_telegram(telegram_id)

    if user_id is None:
        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer(
            "Пользователь не найден. Сначала зарегистрируйтесь.",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    async with SessionLocal() as session:
        await session.execute(
            text(
                """
                DELETE FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        await session.commit()

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "✅ Аккаунт и связанные данные успешно удалены.",
        reply_markup=start_keyboard(is_registered=False),
    )
    await callback.answer()


@router.callback_query(F.data == "back_account_management")
async def back_account_management_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id

    if not await is_registered(telegram_id):
        await callback.message.edit_text(
            "Сначала зарегистрируйтесь.",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "⚙️ <b>Управление аккаунтом</b>\n\n"
        "Здесь вы можете:\n"
        "• <b>🔌 Отвязать Telegram</b> — бот перестанет быть связан с аккаунтом, "
        "но сам аккаунт в сервисе сохранится.\n"
        "• <b>🗑 Удалить аккаунт</b> — аккаунт и связанные данные сервиса будут удалены.\n\n"
        "⚠️ После отвязки или удаления текущее меню будет очищено.\n\n"
        "Выберите нужное действие:",
        parse_mode="HTML",
        reply_markup=account_management_keyboard(),
    )
    await callback.answer()