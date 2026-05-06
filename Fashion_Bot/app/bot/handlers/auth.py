from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import aiohttp
import logging

from app.core.config import settings
from app.bot.states import LinkWebState
from app.bot.keyboards import (
    start_keyboard,
    back_keyboard,
    cancel_input_keyboard,
)

router = Router()
logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)

API_BASE_URL = "http://fashion-api-service:8000"


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



@router.callback_query(F.data == "register")
async def register_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

    if await is_registered(telegram_id):
        text = (
            "Вы уже зарегистрированы!\n"
            "Используйте меню ниже для работы с ботом."
        )
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=start_keyboard(is_registered=True),
        )
        await callback.answer()
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/auth/register-telegram",
                json={
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                }
            ) as resp:
                if resp.status == 200:
                    text = (
                        "✅ <b>Регистрация успешна!</b>\n\n"
                        "Теперь вы можете:\n"
                        "• Загружать фото одежды\n"
                        "• Получать персональные рекомендации\n"
                        "• Привязать веб-аккаунт для полного доступа\n\n"
                        "Выберите нужное действие ниже."
                    )
                    await callback.message.edit_text(
                        text,
                        parse_mode="HTML",
                        reply_markup=start_keyboard(is_registered=True),
                    )
                    await state.update_data(
                        current_message_id=callback.message.message_id,
                        current_text=text,
                        current_keyboard="start",
                    )
                    await callback.answer()
                else:
                    error_data = await resp.json()
                    await callback.answer(
                        f"Ошибка регистрации: {error_data.get('detail', 'Неизвестная ошибка')}",
                        show_alert=True
                    )
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        await callback.answer("Ошибка связи с сервером", show_alert=True)



@router.message(LinkWebState.waiting_for_link_code)
async def process_link_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    link_message_id = data.get("link_message_id")

    # Проверяем код через API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/auth/link/telegram/verify",
                json={
                    "code": code,
                    "telegram_id": message.from_user.id,
                    "username": message.from_user.username,
                    "first_name": message.from_user.first_name,
                    "last_name": message.from_user.last_name,
                }
            ) as resp:
                if resp.status == 200:
                    # Код верный - обновляем сообщение
                    success_text = (
                        "✅ <b>Telegram успешно привязан!</b>\n\n"
                        "Теперь вы можете использовать как веб-версию, так и бота.\n"
                        "Все данные синхронизированы."
                    )
                    
                    if link_message_id:
                        try:
                            await message.bot.edit_message_text(
                                chat_id=message.chat.id,
                                message_id=link_message_id,
                                text=success_text,
                                parse_mode="HTML",
                                reply_markup=back_keyboard()
                            )
                        except Exception:
                            await message.answer(success_text, parse_mode="HTML", reply_markup=back_keyboard())
                    else:
                        await message.answer(success_text, parse_mode="HTML", reply_markup=back_keyboard())
                    
                    await state.clear()
                else:

                    error_text = (
                        "🔑 <b>Вход по коду из веб-версии</b>\n\n"
                        "❌ Код не найден или уже использован.\n"
                        "Проверьте код и попробуйте снова.\n\n"
                        "1. Войдите в веб-версию под своим аккаунтом (email + пароль).\n"
                        "2. Получите одноразовый код для связи с Telegram.\n"
                        "3. Отправьте этот код следующим сообщением."
                    )
                    
                    if link_message_id:
                        try:
                            await message.bot.edit_message_text(
                                chat_id=message.chat.id,
                                message_id=link_message_id,
                                text=error_text,
                                parse_mode="HTML",
                                reply_markup=cancel_input_keyboard()
                            )
                        except Exception:
                            sent = await message.answer(error_text, parse_mode="HTML", reply_markup=cancel_input_keyboard())
                            await state.update_data(link_message_id=sent.message_id)
                    else:
                        sent = await message.answer(error_text, parse_mode="HTML", reply_markup=cancel_input_keyboard())
                        await state.update_data(link_message_id=sent.message_id)

    except Exception as e:
        logger.error(f"Error verifying link code: {e}")
        error_text = (
            "🔑 <b>Вход по коду из веб-версии</b>\n\n"
            "❌ Ошибка связи с сервером. Попробуйте позже.\n\n"
            "1. Войдите в веб-версию под своим аккаунтом (email + пароль).\n"
            "2. Получите одноразовый код для связи с Telegram.\n"
            "3. Отправьте этот код следующим сообщением."
        )
        
        if link_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=link_message_id,
                    text=error_text,
                    parse_mode="HTML",
                    reply_markup=cancel_input_keyboard()
                )
            except Exception:
                sent = await message.answer(error_text, parse_mode="HTML", reply_markup=cancel_input_keyboard())
                await state.update_data(link_message_id=sent.message_id)
        else:
            sent = await message.answer(error_text, parse_mode="HTML", reply_markup=cancel_input_keyboard())
            await state.update_data(link_message_id=sent.message_id)