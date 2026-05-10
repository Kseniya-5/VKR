from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.bot.states import ProfileEditState, LinkWebState, UploadPhotosState
from app.core.security import create_access_token
from app.core.config import settings
from sqlalchemy import text as sql_text 
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import aiohttp
import asyncio
import logging
import json
import re
from uuid import uuid4
from pathlib import Path


from app.core.config import settings
from app.bot.keyboards import (
    start_keyboard,
    back_keyboard,
    profile_keyboard,
    cancel_input_keyboard,
    link_web_keyboard,
    link_from_web_keyboard,
    view_photos_keyboard,
    confirm_delete_photos_keyboard,
    account_management_keyboard,
    confirm_unlink_telegram_keyboard,
    confirm_delete_account_keyboard,
    back_to_link_web_keyboard,
    fashion_action_menu_keyboard,
    choose_photo_for_action_keyboard,
    choose_model_keyboard,
    fashion_action_result_keyboard,
)


router = Router()
upload_locks: dict[int, asyncio.Lock] = {}


engine = create_async_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
)


SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


logger = logging.getLogger(__name__)
API_BASE_URL = settings.api_base_url.rstrip("/")
WEB_BASE_URL = settings.public_base_url.rstrip("/")
MEDIA_ROOT = Path(getattr(settings, "media_root", "/app/media"))


async def is_user_registered(telegram_id: int) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            sql_text(
                """
                SELECT 1
                FROM telegram_accounts
                WHERE telegram_id = :telegram_id
                LIMIT 1
                """
            ),
            {"telegram_id": telegram_id},
        )
        return result.scalar_one_or_none() is not None


async def get_profile_row(telegram_id: int):
    async with SessionLocal() as session:
        result = await session.execute(
            sql_text(
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
        return result.mappings().first()


async def get_profile_text(telegram_id: int) -> str | None:
    row = await get_profile_row(telegram_id)

    if not row:
        return None

    username = row["username"] or "не указан"
    first_name = row["first_name"] or "не указано"
    last_name = row["last_name"] or "не указано"
    email = row["email"] or "добавится автоматически после связи с веб-версией"

    telegram_username = f"@{username}" if username != "не указан" else "не указан"

    return (
        "👤 <b>Ваш профиль</b>\n\n"
        f"Ник в Telegram: {telegram_username}\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Email: {email}"
    )


def has_last_name(row) -> bool:
    if not row:
        return False
    value = row["last_name"]
    return value is not None and str(value).strip() != ""


def get_help_text() -> str:
    return (
        "❔ <b>Помощь</b>\n\n"
        "Fashion Bot помогает управлять персональным гардеробом и стилем.\n\n"
        "<b>Основные функции:</b>\n"
        "• 👤 Профиль — просмотр данных аккаунта\n"
        "• ⚙️ Управление аккаунтом — отвязка Telegram или удаление аккаунта\n"
        "• 🔗 Веб-версия — связь с сайтом\n"
        "• 📸 Загрузить фото — отправка фото одежды\n"
        "• 🖼 Посмотреть фото — просмотр загруженных фото и удаление\n"
        "• 👗 Получить рекомендации — советы по подбору одежды\n"
        "• 🧥 Собрать образ — помощь в составлении комплекта"
    )


def insert_warning_into_text(original_text: str) -> str:
    """
    Вставляет предупреждение между заголовком и остальным текстом с пустыми строками
    """
    warning = (
        "\n\n🥺 <b>Извините, но сейчас я ожидаю нажатие кнопок.</b>\n"
        "Пожалуйста, выберите нужное действие ниже.\n"
    )

    if "\n\n" in original_text:
        parts = original_text.split("\n\n", 1)
        return parts[0] + warning + "\n" + parts[1]
    else:
        lines = original_text.split("\n", 1)
        if len(lines) > 1:
            return lines[0] + warning + "\n" + lines[1]
        else:
            return original_text + warning


async def show_main_menu(
    target_message,
    state: FSMContext,
    is_registered: bool,
    warning: bool = False,
):
    if warning:
        text_value = (
            "🥺 <b>Извините, но сейчас я ожидаю нажатие кнопок.</b>\n"
            "Пожалуйста, выберите нужное действие ниже."
        )
    else:
        if is_registered:
            text_value = (
                "🏠 <b>Главное меню Fashion Bot!</b>\n\n"
                "Я помогаю управлять <b>персональным гардеробом и стилем</b>.\n"
                "Выберите нужное действие ниже."
            )
        else:
            text_value = (
                "👗 <b>Добро пожаловать в Fashion Bot!</b>\n\n"
                "Я помогаю управлять <b>персональным гардеробом и стилем</b>: "
                "храню фото вещей, подсказываю удачные сочетания и собираю образы на каждый день.\n\n"
                "Начните с регистрации, чтобы я запомнил ваш гардероб и смог давать персональные рекомендации.\n"
                "Чтобы начать, нажмите кнопку <b>«📝 Зарегистрироваться»</b>."
            )

    sent_message = await target_message.answer(
        text_value,
        parse_mode="HTML",
        reply_markup=start_keyboard(is_registered=is_registered),
    )

    await state.update_data(
        main_menu_message_id=sent_message.message_id,
        current_message_id=sent_message.message_id,
        current_text=text_value,
        current_keyboard="start",
    )
    return sent_message


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    is_registered = await is_user_registered(telegram_id)

    await show_main_menu(
        target_message=message,
        state=state,
        is_registered=is_registered,
        warning=False,
    )


@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    is_registered = await is_user_registered(telegram_id)

    data = await state.get_data()
    photo_message_ids = data.get("photo_message_ids", [])
    menu_message_id = data.get("menu_message_id")
    selected_fashion_photo_message_id = data.get("selected_fashion_photo_message_id")

    if selected_fashion_photo_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=selected_fashion_photo_message_id,
            )
        except Exception:
            pass

    for mid in photo_message_ids:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=mid,
            )
        except Exception:
            pass

    if menu_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=menu_message_id,
            )
        except Exception:
            pass

    await state.clear()

    if is_registered:
        text_value = (
            "🏠 <b>Главное меню Fashion Bot!</b>\n\n"
            "Я помогаю управлять <b>персональным гардеробом и стилем</b>.\n"
            "Выберите нужное действие ниже."
        )
    else:
        text_value = (
            "👗 <b>Добро пожаловать в Fashion Bot!</b>\n\n"
            "Чтобы начать, нажмите кнопку <b>«📝 Зарегистрироваться»</b>."
        )

    try:
        await callback.message.edit_text(
            text_value,
            parse_mode="HTML",
            reply_markup=start_keyboard(is_registered=is_registered),
        )
        await state.update_data(
            main_menu_message_id=callback.message.message_id,
            current_message_id=callback.message.message_id,
            current_text=text_value,
            current_keyboard="start",
        )
    except Exception:
        sent = await callback.message.answer(
            text_value,
            parse_mode="HTML",
            reply_markup=start_keyboard(is_registered=is_registered),
        )
        await state.update_data(
            main_menu_message_id=sent.message_id,
            current_message_id=sent.message_id,
            current_text=text_value,
            current_keyboard="start",
        )

    await callback.answer()


@router.message(Command("help"))
async def help_cmd(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    is_registered = await is_user_registered(telegram_id)

    text = get_help_text()

    sent = await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=back_keyboard() if is_registered else start_keyboard(is_registered=False),
    )

    await state.update_data(
        current_message_id=sent.message_id,
        current_text=text,
        current_keyboard="back" if is_registered else "start",
    )


@router.callback_query(F.data == "open_help")
async def open_help_callback(callback: CallbackQuery, state: FSMContext):
    text = get_help_text()

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="back",
    )

    await callback.answer()


@router.callback_query(F.data == "account_management")
async def account_management_callback(callback: CallbackQuery, state: FSMContext):
    if not await is_user_registered(callback.from_user.id):
        text = "Сначала нужно зарегистрироваться."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    text = (
        "⚙️ <b>Управление аккаунтом</b>\n\n"
        "Здесь вы можете:\n"
        "• 🔌 Отвязать Telegram — бот перестанет быть связан с аккаунтом, но сам аккаунт в сервисе сохранится.\n"
        "• 🗑 Удалить аккаунт — аккаунт и связанные данные сервиса будут удалены.\n\n"
        "⚠️ После отвязки или удаления текущее меню будет очищено.\n\n"
        "Выберите нужное действие:"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=account_management_keyboard(),
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="account_management",
    )

    await callback.answer()


@router.callback_query(F.data == "confirm_unlink_telegram")
async def confirm_unlink_telegram_callback(callback: CallbackQuery, state: FSMContext):
    if not await is_user_registered(callback.from_user.id):
        text = "Сначала нужно зарегистрироваться."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    text = (
        "⚠️ <b>Подтверждение отвязки Telegram</b>\n\n"
        "После отвязки бот больше не будет связан с вашим аккаунтом.\n"
        "Сам аккаунт в сервисе сохранится.\n"
        "Текущее меню будет удалено.\n\n"
        "Вы точно хотите отвязать Telegram?"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=confirm_unlink_telegram_keyboard(),
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="confirm_unlink",
    )

    await callback.answer()


@router.callback_query(F.data == "confirm_delete_account")
async def confirm_delete_account_callback(callback: CallbackQuery, state: FSMContext):
    if not await is_user_registered(callback.from_user.id):
        text = "Сначала нужно зарегистрироваться."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    text = (
        "⚠️ <b>Подтверждение удаления аккаунта</b>\n\n"
        "После удаления аккаунт и все связанные данные будут безвозвратно удалены.\n"
        "Текущее меню будет удалено.\n\n"
        "Вы точно хотите удалить аккаунт?"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=confirm_delete_account_keyboard(),
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="confirm_delete_account",
    )

    await callback.answer()

class AccountDeletion(StatesGroup):
    processing = State()

@router.callback_query(F.data == "do_delete_account")
async def do_delete_account_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    if not await is_user_registered(telegram_id):
        await callback.answer("Вы уже не зарегистрированы", show_alert=True)
        await state.clear()
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    await state.set_state(AccountDeletion.processing)

    async with SessionLocal() as session:
        result = await session.execute(
            sql_text(
                """
                SELECT user_id
                FROM telegram_accounts
                WHERE telegram_id = :telegram_id
                LIMIT 1
                """
            ),
            {"telegram_id": telegram_id},
        )
        row = result.mappings().first()
        
        if not row:
            await callback.answer("Ошибка: пользователь не найден", show_alert=True)
            await state.clear()
            return
        
        user_id = str(row["user_id"])

    access_token = create_access_token(subject=user_id)

    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.delete(
                f"{API_BASE_URL}/users/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json={"confirm_text": "DELETE"}
            ) as resp:
                
                if resp.status == 200:
                    message_text = (
                        "✅ <b>Аккаунт успешно удалён</b>\n\n"
                        "Пожалуйста, выберите нужное действие ниже.\n\n"
                        "Все ваши данные были удалены из системы.\n"
                        "Вы можете зарегистрироваться снова"
                    )
                    
                    await state.set_state(None)
                    
                    await callback.message.edit_text(
                        message_text, 
                        parse_mode="HTML",
                        reply_markup=start_keyboard(is_registered=False)
                    )

                    await state.update_data(
                        current_message_id=callback.message.message_id,
                        current_text=message_text,
                        current_keyboard="start",
                    )
                    
                    data = await state.get_data()
                    
                    await callback.answer()
                else:
                    error_data = await resp.json()
                    await state.clear()
                    await callback.answer(
                        f"Ошибка удаления: {error_data.get('detail', 'Неизвестная ошибка')}",
                        show_alert=True
                    )
    except Exception as e:
        await state.clear()
        await callback.answer("Ошибка связи с сервером", show_alert=True)


class TelegramUnlink(StatesGroup):
    processing = State()


@router.callback_query(F.data == "do_unlink_telegram")
async def do_unlink_telegram_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    if not await is_user_registered(telegram_id):
        await callback.answer("Вы уже не зарегистрированы", show_alert=True)
        await state.clear()
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    await state.set_state(TelegramUnlink.processing)

    async with SessionLocal() as session:
        result = await session.execute(
            sql_text(
                """
                SELECT user_id
                FROM telegram_accounts
                WHERE telegram_id = :telegram_id
                LIMIT 1
                """
            ),
            {"telegram_id": telegram_id},
        )
        row = result.mappings().first()
        
        if not row:
            await callback.answer("Ошибка: пользователь не найден", show_alert=True)
            await state.clear()
            return
        
        user_id = str(row["user_id"])

    access_token = create_access_token(subject=user_id)

    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.delete(
                f"{API_BASE_URL}/users/me/telegram-link",
                headers={"Authorization": f"Bearer {access_token}"}
            ) as resp:
                if resp.status == 200:
                    message_text = (
                        "✅ <b>Telegram отвязан</b>\n\n"
                        "Пожалуйста, выберите нужное действие ниже.\n\n"
                        "Ваш Telegram больше не связан с аккаунтом.\n"
                        "Аккаунт в системе сохранён, доступен через веб-версию.\n\n"
                        "Вы можете зарегистрироваться снова"
                    )
                    
                    await state.set_state(None)
                    
                    await callback.message.edit_text(
                        message_text, 
                        parse_mode="HTML",
                        reply_markup=start_keyboard(is_registered=False)
                    )
                    
                    await state.update_data(
                        current_message_id=callback.message.message_id,
                        current_text=message_text,
                        current_keyboard="start",
                    )
                    
                    await callback.answer()
                else:
                    error_data = await resp.json()
                    await state.clear()
                    await callback.answer(
                        f"Ошибка отвязки: {error_data.get('detail', 'Неизвестная ошибка')}",
                        show_alert=True
                    )
    except Exception as e:
        logger.error(f"Error unlinking Telegram: {e}")
        await state.clear()
        await callback.answer("Ошибка связи с сервером", show_alert=True)

@router.message(Command("link"))
async def cmd_link(message: Message, state: FSMContext):
    await state.set_state(LinkWebState.waiting_for_link_code)

    text = (
        "🔑 <b>Вход по коду из веб-версии</b>\n\n"
        "1. Войдите в веб-версию под своим аккаунтом (email + пароль).\n"
        "2. Получите одноразовый код для связи с Telegram.\n"
        "3. Отправьте этот код следующим сообщением."
    )

    sent = await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=cancel_input_keyboard(),  
    )

    await state.update_data(
        link_message_id=sent.message_id,
        current_message_id=sent.message_id,
        current_text=text,
        current_keyboard="cancel",  
    )


# ============================================================
# Регистрация, профиль, удаление и тд
# ============================================================

@router.callback_query(F.data == "start_register")
async def start_register_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

    if await is_user_registered(telegram_id):
        message_text = "✅ Ваш Telegram уже зарегистрирован и привязан к аккаунту."
        
        await state.clear()
        
        try:
            await callback.message.delete()
        except Exception:
            pass
    
        sent_message = await callback.message.answer(
            message_text,
            parse_mode="HTML",
            reply_markup=start_keyboard(is_registered=True),
        )
        
        await state.update_data(
            current_message_id=sent_message.message_id,
            current_text=message_text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    async with SessionLocal() as session:
        user_result = await session.execute(
            sql_text("INSERT INTO users DEFAULT VALUES RETURNING id")
        )
        user_id = user_result.scalar_one()

        await session.execute(
            sql_text(
                """
                INSERT INTO telegram_accounts (
                    telegram_id,
                    user_id,
                    username,
                    first_name,
                    last_name
                ) VALUES (
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

    message_text = (
        "✅ <b>Регистрация выполнена успешно!</b>\n\n"
        "Telegram сохранён и привязан к вашему аккаунту.\n"
        "Теперь вы можете пользоваться функциями бота."
    )

    await state.clear()
    
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    sent_message = await callback.message.answer(
        message_text,
        parse_mode="HTML",
        reply_markup=start_keyboard(is_registered=True),
    )

    await state.update_data(
        current_message_id=sent_message.message_id,
        current_text=message_text,
        current_keyboard="start",
    )

    await callback.answer()


async def get_user_id_by_telegram(telegram_id: int) -> str | None:
    async with SessionLocal() as session:
        result = await session.execute(
            sql_text(
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


@router.callback_query(F.data == "start_link_from_web")
async def start_link_from_web_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LinkWebState.waiting_for_link_code)

    text = (
        "🔑 <b>Вход по коду из веб-версии</b>\n\n"
        "1. Войдите в веб-версию по email и паролю.\n"
        "2. Получите одноразовый код для связи с Telegram.\n"
        "3. Отправьте этот код следующим сообщением.\n\n"
        "⚠️ Код действует ограниченное время."
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=link_from_web_keyboard(),
    )

    await state.update_data(
        link_message_id=callback.message.message_id,
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="link_from_web",
    )

    await callback.answer()


def has_last_name(row) -> bool:
    if not row:
        return False
    value = row["last_name"]
    return value is not None and str(value).strip() != ""


@router.callback_query(F.data == "open_profile")
async def open_profile_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    telegram_id = callback.from_user.id
    row = await get_profile_row(telegram_id)
    profile_text = await get_profile_text(telegram_id)

    if profile_text is None or row is None:
        text = (
            "Профиль ещё не создан.\n"
            "Сначала нажмите кнопку «📝 Зарегистрироваться»."
        )
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        profile_text,
        parse_mode="HTML",
        reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
    )

    await state.update_data(
        profile_message_id=callback.message.message_id,
        current_message_id=callback.message.message_id,
        current_text=profile_text,
        current_keyboard="profile",
    )

    await callback.answer()


@router.callback_query(F.data == "edit_last_name")
async def edit_last_name_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEditState.waiting_for_last_name)

    text = (
        "✏️ <b>Редактирование фамилии</b>\n\n"
        "Введите фамилию следующим сообщением."
    )

    await state.update_data(
        profile_message_id=callback.message.message_id,
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="cancel",
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=cancel_input_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_profile_edit")
async def cancel_profile_edit_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    telegram_id = callback.from_user.id
    row = await get_profile_row(telegram_id)
    profile_text = await get_profile_text(telegram_id)

    if profile_text is None or row is None:
        text = "Профиль ещё не создан."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        profile_text,
        parse_mode="HTML",
        reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
    )

    await state.update_data(
        profile_message_id=callback.message.message_id,
        current_message_id=callback.message.message_id,
        current_text=profile_text,
        current_keyboard="profile",
    )

    await callback.answer("Редактирование отменено")


@router.callback_query(F.data == "edit_first_name")
async def edit_first_name_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEditState.waiting_for_first_name)

    text = (
        "✍️ <b>Редактирование имени</b>\n\n"
        "Введите имя следующим сообщением."
    )

    await state.update_data(
        profile_message_id=callback.message.message_id,
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="cancel",
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=cancel_input_keyboard(),
    )
    await callback.answer()


def is_valid_name(name: str) -> bool:
    """
    Разрешаем только буквы (включая кириллицу), пробелы, дефисы
    Длина: 1-50 символов
    """
    if not name or len(name) > 50:
        return False
    pattern = r"^[a-zA-Zа-яА-ЯёЁ\s\-]+$"
    return bool(re.match(pattern, name))



@router.message(ProfileEditState.waiting_for_first_name)
async def process_first_name(message: Message, state: FSMContext):
    if not message.text:
        try:
            await message.delete()
        except Exception:
            pass
        return

    telegram_id = message.from_user.id
    first_name = message.text.strip()
    data = await state.get_data()
    profile_message_id = data.get("profile_message_id")

    if not is_valid_name(first_name):
        try:
            await message.delete()
        except Exception:
            pass

        row = await get_profile_row(telegram_id)
        current_profile = await get_profile_text(telegram_id)

        error_text = (
            "✍️ <b>Редактирование имени</b>\n\n"
            "❌ Имя не изменилось, так как оно может содержать только буквы, пробелы и дефисы (до 50 символов)\n"
            "Пожалуйста, введите корректное имя.\n\n"
            f"{current_profile}"
        )

        if profile_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=profile_message_id,
                    text=error_text,
                    parse_mode="HTML",
                    reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
                )

                await state.clear()
                await state.update_data(
                    profile_message_id=profile_message_id,
                    current_message_id=profile_message_id,
                    current_text=error_text,
                    current_keyboard="profile",
                )
                return
            except Exception:
                pass

        sent = await message.answer(
            error_text,
            parse_mode="HTML",
            reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
        )
        await state.clear()
        await state.update_data(
            profile_message_id=sent.message_id,
            current_message_id=sent.message_id,
            current_text=error_text,
            current_keyboard="profile",
        )
        return

    async with SessionLocal() as session:
        await session.execute(
            sql_text(
                """
                UPDATE telegram_accounts
                SET first_name = :first_name
                WHERE telegram_id = :telegram_id
                """
            ),
            {
                "first_name": first_name,
                "telegram_id": telegram_id,
            },
        )
        await session.commit()

    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass

    row = await get_profile_row(telegram_id)
    profile_text = await get_profile_text(telegram_id)

    updated_text = (
        f"{profile_text.split(chr(10) + chr(10))[0]}\n\n"
        f"✅ Имя обновлено\n\n"
        f"{chr(10).join(profile_text.split(chr(10) + chr(10))[1:])}"
    )

    if profile_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=profile_message_id,
                text=updated_text,
                parse_mode="HTML",
                reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
            )
            await state.update_data(
                profile_message_id=profile_message_id,
                current_message_id=profile_message_id,
                current_text=updated_text,
                current_keyboard="profile",
            )
            return
        except Exception:
            pass

    sent = await message.answer(
        updated_text,
        parse_mode="HTML",
        reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
    )
    await state.update_data(
        profile_message_id=sent.message_id,
        current_message_id=sent.message_id,
        current_text=updated_text,
        current_keyboard="profile",
    )


@router.message(ProfileEditState.waiting_for_last_name)
async def process_last_name(message: Message, state: FSMContext):
    if not message.text:
        try:
            await message.delete()
        except Exception:
            pass
        return

    telegram_id = message.from_user.id
    last_name = message.text.strip()
    data = await state.get_data()
    profile_message_id = data.get("profile_message_id")

    if not is_valid_name(last_name):
        try:
            await message.delete()
        except Exception:
            pass

        row = await get_profile_row(telegram_id)
        current_profile = await get_profile_text(telegram_id)

        error_text = (
            "✏️ <b>Редактирование фамилии</b>\n\n"
            "❌ Фамилия не изменилась, так как она может содержать только буквы, пробелы и дефисы (до 50 символов)\n"
            "Пожалуйста, введите корректную фамилию\n\n"
            f"{current_profile}"
        )

        if profile_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=profile_message_id,
                    text=error_text,
                    parse_mode="HTML",
                    reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
                )
                await state.clear()
                await state.update_data(
                    profile_message_id=profile_message_id,
                    current_message_id=profile_message_id,
                    current_text=error_text,
                    current_keyboard="profile",
                )
                return
            except Exception:
                pass

        sent = await message.answer(
            error_text,
            parse_mode="HTML",
            reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
        )
        await state.clear()
        await state.update_data(
            profile_message_id=sent.message_id,
            current_message_id=sent.message_id,
            current_text=error_text,
            current_keyboard="profile",
        )
        return

    async with SessionLocal() as session:
        await session.execute(
            sql_text(
                """
                UPDATE telegram_accounts
                SET last_name = :last_name
                WHERE telegram_id = :telegram_id
                """
            ),
            {
                "last_name": last_name,
                "telegram_id": telegram_id,
            },
        )
        await session.commit()

    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass

    row = await get_profile_row(telegram_id)
    profile_text = await get_profile_text(telegram_id)

    updated_text = (
        f"{profile_text.split(chr(10) + chr(10))[0]}\n\n"
        f"✅ Фамилия обновлена\n\n"
        f"{chr(10).join(profile_text.split(chr(10) + chr(10))[1:])}"
    )

    if profile_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=profile_message_id,
                text=updated_text,
                parse_mode="HTML",
                reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
            )
            await state.update_data(
                profile_message_id=profile_message_id,
                current_message_id=profile_message_id,
                current_text=updated_text,
                current_keyboard="profile",
            )
            return
        except Exception:
            pass

    sent = await message.answer(
        updated_text,
        parse_mode="HTML",
        reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
    )
    await state.update_data(
        profile_message_id=sent.message_id,
        current_message_id=sent.message_id,
        current_text=updated_text,
        current_keyboard="profile",
    )


@router.message(LinkWebState.waiting_for_link_code)
async def process_link_code(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    data = await state.get_data()
    link_message_id = data.get("link_message_id")

    telegram_id = message.from_user.id

    try:
        await message.delete()
    except Exception:
        pass

    if not code:
        if link_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=link_message_id,
                    text=(
                        "🔑 <b>Вход по коду из веб-версии</b>\n\n"
                        "Пожалуйста, отправьте код текстом одним сообщением."
                    ),
                    parse_mode="HTML",
                    reply_markup=back_keyboard(),
                )
                return
            except Exception:
                pass

        await message.answer(
            "Пожалуйста, отправьте код текстом одним сообщением.",
            reply_markup=back_keyboard(),
        )
        return

    async with SessionLocal() as session:
        result = await session.execute(
            sql_text(
                """
                SELECT code, user_id, expires_at
                FROM account_link_codes
                WHERE code = :code
                LIMIT 1
                """
            ),
            {"code": code},
        )
        row = result.mappings().first()

        if not row:
            if link_message_id:
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=link_message_id,
                        text=(
                            "🔑 <b>Вход по коду из веб-версии</b>\n\n"
                            "❌ Код не найден или уже использован.\n"
                            "Проверьте код и попробуйте снова."
                        ),
                        parse_mode="HTML",
                        reply_markup=back_keyboard(),
                    )
                    return
                except Exception:
                    pass

            await message.answer(
                "❌ Код не найден или уже использован.\n"
                "Проверьте код и попробуйте снова.",
                reply_markup=back_keyboard(),
            )
            return

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        expires_at = row["expires_at"]
        user_id = row["user_id"]

        if expires_at < now:
            await session.execute(
                sql_text("DELETE FROM account_link_codes WHERE code = :code"),
                {"code": code},
            )
            await session.commit()

            await state.clear()

            if link_message_id:
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=link_message_id,
                        text=(
                            "🔑 <b>Вход по коду из веб-версии</b>\n\n"
                            "⏰ Срок действия кода истёк.\n"
                            "Сгенерируйте новый код в веб-версии."
                        ),
                        parse_mode="HTML",
                        reply_markup=start_keyboard(is_registered=False),
                    )
                    return
                except Exception:
                    pass

            await message.answer(
                "⏰ Срок действия кода истёк.\n"
                "Сгенерируйте новый код в веб-версии.",
                reply_markup=start_keyboard(is_registered=False),
            )
            return

        existing_user_id = await get_user_id_by_telegram(telegram_id)
        if existing_user_id and str(existing_user_id) != str(user_id):
            await state.clear()

            if link_message_id:
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=link_message_id,
                        text=(
                            "⚠️ Этот Telegram уже привязан к другому аккаунту.\n\n"
                            "Сначала отвяжите его в настройках, а затем попробуйте снова."
                        ),
                        reply_markup=start_keyboard(is_registered=True),
                    )
                    return
                except Exception:
                    pass

            await message.answer(
                "⚠️ Этот Telegram уже привязан к другому аккаунту.\n"
                "Сначала отвяжите его в настройках.",
                reply_markup=start_keyboard(is_registered=True),
            )
            return

        await session.execute(
            sql_text(
                """
                INSERT INTO telegram_accounts (
                    telegram_id,
                    user_id,
                    username,
                    first_name,
                    last_name
                ) VALUES (
                    :telegram_id,
                    :user_id,
                    :username,
                    :first_name,
                    :last_name
                )
                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
                """
            ),
            {
                "telegram_id": telegram_id,
                "user_id": str(user_id),
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name,
            },
        )

        await session.execute(
            sql_text("DELETE FROM account_link_codes WHERE code = :code"),
            {"code": code},
        )

        await session.commit()

    await state.clear()

    success_text = (
        "✅ <b>Telegram успешно привязан к аккаунту из веб-версии</b>\n\n"
        "Теперь вы можете пользоваться ботом и веб-версией как одним аккаунтом"
    )

    if link_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=link_message_id,
                text=success_text,
                parse_mode="HTML",
                reply_markup=start_keyboard(is_registered=True),
            )
            return
        except Exception:
            pass

    await message.answer(
        success_text,
        parse_mode="HTML",
        reply_markup=start_keyboard(is_registered=True),
    )

@router.callback_query(F.data == "generate_web_link")
async def generate_web_link_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/auth/dev-token-for-telegram",
                params={"telegram_id": telegram_id},
            ) as resp:
                resp_text = await resp.text()
                if resp.status != 200:
                    logger.error(
                        "dev-token-for-telegram failed: status=%s body=%s",
                        resp.status,
                        resp_text,
                    )
                    text = (
                        "😔 Не удалось сгенерировать ссылку для входа в веб. "
                        "Попробуйте позже."
                    )
                    await callback.message.edit_text(
                        text,
                        reply_markup=back_to_link_web_keyboard(),
                    )
                    await state.update_data(
                        current_message_id=callback.message.message_id,
                        current_text=text,
                        current_keyboard="back_to_link_web",
                    )
                    await callback.answer()
                    return

                data = json.loads(resp_text)
    except Exception as e:
        logger.exception("Error in generate_web_link_callback: %s", e)
        text = "😔 Не удалось связаться с сервером. Попробуйте позже."
        await callback.message.edit_text(
            text,
            reply_markup=back_to_link_web_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back_to_link_web",
        )
        await callback.answer()
        return

    access_token = data.get("access_token")
    if not access_token:
        logger.error("dev-token-for-telegram returned no access_token: %s", data)
        text = "😔 Сервер не вернул токен. Попробуйте позже."
        await callback.message.edit_text(
            text,
            reply_markup=back_to_link_web_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back_to_link_web",
        )
        await callback.answer()
        return

    web_link = f"{WEB_BASE_URL}/from-telegram?token={access_token}"

    text = (
        "🔗 <b>Ссылка для первого входа в веб-версию</b>\n\n"
        "Эта ссылка нужна, если у вас ещё нет веб-аккаунта. "
        "По ней вы откроете веб-версию и создадите email+пароль для текущего Telegram-профиля.\n\n"
        f"{web_link}"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_to_link_web_keyboard(),
        disable_web_page_preview=False,
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="back_to_link_web",
    )

    await callback.answer()


@router.callback_query(F.data == "link_existing_web")
async def link_existing_web_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    access_token = await _get_access_token_for_telegram(telegram_id)
    if not access_token:
        text = "😔 Не удалось получить токен для привязки. Попробуйте позже."
        await callback.message.edit_text(
            text,
            reply_markup=back_to_link_web_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back_to_link_web",
        )
        await callback.answer()
        return

    web_link = f"{WEB_BASE_URL}/link-existing-web?token={access_token}"

    text = (
        "🔗 <b>Связать Telegram с существующим веб-аккаунтом</b>\n\n"
        "Используйте этот вариант, если вы уже зарегистрировались и в Telegram, "
        "и в веб-версии отдельно.\n\n"
        "По ссылке ниже откроется страница, где нужно ввести email и пароль "
        "вашего существующего веб-аккаунта. После подтверждения фотографии из Telegram "
        "и web будут объединены в одном гардеробе.\n\n"
        f"{web_link}"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_to_link_web_keyboard(),
        disable_web_page_preview=False,
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="back_to_link_web",
    )

    await callback.answer()


@router.callback_query(F.data == "link_web")
async def link_web_callback(callback: CallbackQuery, state: FSMContext):
    if not await is_user_registered(callback.from_user.id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    await state.clear()

    text = (
        "🔗 <b>Связь с веб-версией</b>\n\n"
        "Выберите подходящий вариант:\n\n"
        "1. <b>Сгенерировать ссылку для первого входа в веб</b> — если у вас есть Telegram-профиль, "
        "но ещё нет веб-аккаунта. По ссылке вы создадите email и пароль для этого же аккаунта.\n\n"
        "2. <b>Связать с существующим веб-аккаунтом</b> — если вы уже отдельно зарегистрировались "
        "и в Telegram, и в веб-версии. По ссылке вы введёте email/пароль веб-аккаунта, "
        "а я объединю аккаунты и фотографии.\n\n"
        "3. <b>Открыть веб-версию</b> — просто перейти на сайт."
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=link_web_keyboard(),
        disable_web_page_preview=True,
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="link_web",
    )

    await callback.answer()


@router.callback_query(F.data == "open_help")
async def open_help_callback(callback: CallbackQuery, state: FSMContext):
    text = get_help_text()

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="back",
    )

    await callback.answer()

# ============================================================
# Загрузка фото 
# ============================================================

@router.callback_query(F.data == "upload_photo")
async def upload_photo_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/auth/dev-token-for-telegram",
                params={"telegram_id": telegram_id},
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        "upload_photo: dev-token failed status=%s",
                        resp.status,
                    )
                    text = "😔 Не удалось получить токен для загрузки. Попробуйте позже."
                    await callback.message.edit_text(
                        text,
                        reply_markup=back_keyboard(),
                    )
                    await state.update_data(
                        current_message_id=callback.message.message_id,
                        current_text=text,
                        current_keyboard="back",
                    )
                    await callback.answer()
                    return
                data = await resp.json()
                access_token = data["access_token"]
    except Exception as e:
        logger.exception("upload_photo: ошибка получения токена: %s", e)
        text = "😔 Не удалось связаться с сервером. Попробуйте позже."
        await callback.message.edit_text(
            text,
            reply_markup=back_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    text = (
        "📸 <b>Загрузка фото</b>\n\n"
        "Отправьте одно или несколько фотографий подряд, где хорошо видно одежду.\n"
        "Я принимаю форматы: JPG, PNG, HEIC, WEBP — и автоматически "
        "конвертирую их в JPEG для дальнейшей работы.\n\n"
        "Если отправите не фото, я удалю сообщение и напомню, "
        "что можно загружать только изображения."
    )

    await state.set_state(UploadPhotosState.waiting_for_photos)
    await state.update_data(
        upload_message_id=callback.message.message_id,
        uploaded_count=0,
        failed_count=0,
        warning_shown=False,
        access_token=access_token,
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="back",
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


async def _update_upload_summary_message(
    bot,
    chat_id: int,
    upload_message_id: int | None,
    uploaded_count: int,
    failed_count: int,
):
    """
    Обновляет текст сообщения с инструкцией/статусом загрузки.
    """
    if not upload_message_id:
        return

    if uploaded_count > 0 and failed_count == 0:
        if uploaded_count == 1:
            text = (
                "✅ <b>Фото добавлено в ваш гардероб.</b>\n\n"
                "Успешно сохранено: <b>1</b> фото.\n"
                "Можете отправить ещё фото или нажать «Назад», "
                "чтобы вернуться в главное меню."
            )
        else:
            text = (
                "✅ <b>Фото добавлены в ваш гардероб.</b>\n\n"
                f"Успешно сохранено: <b>{uploaded_count}</b> фото.\n"
                "Можете отправить ещё фото или нажать «Назад», "
                "чтобы вернуться в главное меню."
            )
    elif uploaded_count > 0 and failed_count > 0:
        text = (
            "⚠️ <b>Часть фото не удалось сохранить.</b>\n\n"
            f"Успешно сохранено: <b>{uploaded_count}</b>.\n"
            f"Ошибок при сохранении: <b>{failed_count}</b>.\n\n"
            "Попробуйте отправить проблемные фото ещё раз, "
            "или нажмите «Назад», чтобы вернуться в главное меню."
        )
    elif uploaded_count == 0 and failed_count > 0:
        text = (
            "😔 <b>Не удалось сохранить ни одно фото.</b>\n\n"
            "Проверьте формат изображений и попробуйте ещё раз.\n"
            "Я принимаю JPG, PNG, HEIC, WEBP."
        )
    else:
        text = (
            "📸 <b>Загрузка фото</b>\n\n"
            "Отправьте одно или несколько фотографий подряд, где хорошо видно одежду.\n"
            "Я принимаю форматы: JPG, PNG, HEIC, WEBP."
        )

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=upload_message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
    except Exception as e:
        logger.warning("Не удалось обновить upload_message_id=%s: %s", upload_message_id, e)


@router.message(UploadPhotosState.waiting_for_photos)
async def handle_uploaded_photos(message: Message, state: FSMContext):
    chat_id = message.chat.id
    
    if chat_id not in upload_locks:
        upload_locks[chat_id] = asyncio.Lock()
    
    async with upload_locks[chat_id]:
        data = await state.get_data()
        upload_message_id = data.get("upload_message_id")
        uploaded_count = data.get("uploaded_count", 0)
        failed_count = data.get("failed_count", 0)
        warning_shown = data.get("warning_shown", False)
        access_token = data.get("access_token")

        if not message.photo:
            try:
                await message.delete()
            except Exception as e:
                logger.warning("Не удалось удалить сообщение (не фото): %s", e)

            if not warning_shown:
                warning_text = (
                    "📸 <b>Загрузка фото</b>\n\n"
                    "Я могу сохранить только <b>изображения</b>.\n"
                    "Пожалуйста, отправьте фото в формате JPG, PNG, HEIC или WEBP."
                )

                if upload_message_id:
                    try:
                        await message.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=upload_message_id,
                            text=warning_text,
                            parse_mode="HTML",
                            reply_markup=back_keyboard(),
                        )
                    except Exception as e:
                        if "message is not modified" not in str(e).lower():
                            logger.warning("Не удалось отредактировать upload_message: %s", e)
                else:
                    await message.answer(
                        warning_text,
                        parse_mode="HTML",
                        reply_markup=back_keyboard(),
                    )

                await state.update_data(warning_shown=True)
            return

        await state.update_data(warning_shown=False)

        photo = message.photo[-1]
        telegram_file_id = photo.file_id

        try:
            file = await message.bot.get_file(telegram_file_id)
            file_path = file.file_path
        except Exception as e:
            logger.error("Не удалось получить file_path для file_id=%s: %s", telegram_file_id, e)
            failed_count += 1

            await asyncio.sleep(0.2)
            try:
                await message.delete()
            except Exception:
                pass

            await state.update_data(
                uploaded_count=uploaded_count,
                failed_count=failed_count,
            )
            await _update_upload_summary_message(
                bot=message.bot,
                chat_id=message.chat.id,
                upload_message_id=upload_message_id,
                uploaded_count=uploaded_count,
                failed_count=failed_count,
            )
            return

        try:
            file_bytes_io = await message.bot.download_file(file_path)
            file_bytes = file_bytes_io.read()
        except Exception as e:
            logger.error("Не удалось скачать файл для file_id=%s: %s", telegram_file_id, e)
            failed_count += 1

            await asyncio.sleep(0.2)
            try:
                await message.delete()
            except Exception:
                pass

            await state.update_data(
                uploaded_count=uploaded_count,
                failed_count=failed_count,
            )
            await _update_upload_summary_message(
                bot=message.bot,
                chat_id=message.chat.id,
                upload_message_id=upload_message_id,
                uploaded_count=uploaded_count,
                failed_count=failed_count,
            )
            return

        upload_success = False
        try:
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field(
                    "file",
                    file_bytes,
                    filename=f"{telegram_file_id}.jpg",
                    content_type="image/jpeg",
                )
                form_data.add_field("telegram_file_id", telegram_file_id)
                headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
                async with session.post(
                    f"{API_BASE_URL}/photos/upload",
                    data=form_data,
                    headers=headers,
                ) as resp:
                    resp_text = await resp.text()
                    if resp.status == 200:
                        upload_success = True
                        uploaded_count += 1
                    else:
                        logger.error(
                            "API /photos/upload вернул status=%s для file_id=%s. Ответ: %s",
                            resp.status,
                            telegram_file_id,
                            resp_text,
                        )
                        failed_count += 1
        except Exception as e:
            logger.exception("Ошибка при отправке фото в API для file_id=%s: %s", telegram_file_id, e)
            failed_count += 1

        await asyncio.sleep(0.2)
        try:
            await message.delete()
        except Exception as e:
            logger.warning("Не удалось удалить сообщение с фото: %s", e)

        await state.update_data(
            uploaded_count=uploaded_count,
            failed_count=failed_count,
        )

        await _update_upload_summary_message(
            bot=message.bot,
            chat_id=message.chat.id,
            upload_message_id=upload_message_id,
            uploaded_count=uploaded_count,
            failed_count=failed_count,
        )


# ============================================================
# Просмотр фото, удаление
# ============================================================

async def _delete_photo_messages(bot, chat_id: int, photo_message_ids: list[int]):
    """
    Удаляет сообщения с фото из чата.
    """
    for mid in photo_message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

async def _send_photo_from_url(
    callback: CallbackQuery,
    url: str,
    photo_keyboard: InlineKeyboardMarkup,
    filename: str = "photo.jpg",
    access_token: str | None = None,
):
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Не удалось скачать фото: status={resp.status}, url={url}")

            content_type = (resp.headers.get("Content-Type") or "").lower()
            if not content_type.startswith("image/"):
                raise RuntimeError(
                    f"URL вернул не изображение: content_type={content_type}, url={url}"
                )

            content = await resp.read()
            if not content:
                raise RuntimeError(f"Пустой ответ при скачивании фото: url={url}")

    return await callback.message.answer_photo(
        photo=BufferedInputFile(content, filename=filename),
        reply_markup=photo_keyboard,
    )


async def _get_photo_storage_row(photo_id: str, user_id: str | None = None) -> dict | None:
    query = """
        SELECT id, user_id, original_path, telegram_file_id, mime_type, is_active
        FROM user_photos
        WHERE id = :photo_id
        LIMIT 1
    """
    params = {"photo_id": photo_id}

    if user_id:
        query = """
            SELECT id, user_id, original_path, telegram_file_id, mime_type, is_active
            FROM user_photos
            WHERE id = :photo_id
              AND user_id = :user_id
            LIMIT 1
        """
        params["user_id"] = str(user_id)

    async with SessionLocal() as session:
        result = await session.execute(sql_text(query), params)
        row = result.mappings().first()

    if not row or not row["is_active"]:
        return None
    return dict(row)


async def _send_photo_to_chat_by_photo_id(
    *,
    bot,
    chat_id: int,
    photo_id: str,
    access_token: str | None,
    user_id: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    caption: str | None = None,
):
    row = await _get_photo_storage_row(photo_id, user_id=user_id)
    if not row:
        raise RuntimeError(f"Фото не найдено: {photo_id}")

    telegram_file_id = row.get("telegram_file_id")
    if telegram_file_id:
        return await bot.send_photo(
            chat_id=chat_id,
            photo=telegram_file_id,
            caption=caption,
            parse_mode="HTML" if caption else None,
            reply_markup=reply_markup,
        )

    original_path = row.get("original_path")
    if original_path:
        file_path = MEDIA_ROOT / str(original_path)
        if file_path.exists():
            content = file_path.read_bytes()
            if content:
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=BufferedInputFile(content, filename=file_path.name),
                    caption=caption,
                    parse_mode="HTML" if caption else None,
                    reply_markup=reply_markup,
                )

    # Fallback: ask API to return protected file. This helps if the bot pod does not have media mounted yet.
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    url = f"{API_BASE_URL}/photos/{photo_id}/file"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Не удалось скачать фото: status={resp.status}, url={url}, body={body[:200]}"
                )
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if not content_type.startswith("image/"):
                raise RuntimeError(f"URL вернул не изображение: content_type={content_type}, url={url}")
            content = await resp.read()

    return await bot.send_photo(
        chat_id=chat_id,
        photo=BufferedInputFile(content, filename=f"{photo_id}.jpg"),
        caption=caption,
        parse_mode="HTML" if caption else None,
        reply_markup=reply_markup,
    )


async def _send_photo_message_by_photo_info(
    callback: CallbackQuery,
    info: dict,
    photo_keyboard: InlineKeyboardMarkup,
    access_token: str | None,
):
    photo_id = str(info["id"])
    user_id = None
    telegram_id = callback.from_user.id
    maybe_user_id = await get_user_id_by_telegram(telegram_id)
    if maybe_user_id:
        user_id = str(maybe_user_id)

    return await _send_photo_to_chat_by_photo_id(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        photo_id=photo_id,
        access_token=access_token,
        user_id=user_id,
        reply_markup=photo_keyboard,
    )


async def _fetch_photos_page(
    access_token: str,
    page: int,
    page_size: int = 10,
) -> dict:
    """
    Получает страницу фото от API с авторизацией.
    """
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get(
            f"{API_BASE_URL}/photos",
            params={"page": page, "page_size": page_size},
            headers=headers,
        ) as resp:
            if resp.status != 200:
                logger.error(
                    "_fetch_photos_page: status=%s page=%s",
                    resp.status,
                    page,
                )
                return {"total": 0, "items": []}
            data = await resp.json()
            return data


async def _get_access_token_for_telegram(telegram_id: int) -> str | None:
    """
    Получает временный токен для API для текущего telegram_id.
    Возвращает access_token или None при ошибке.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/auth/dev-token-for-telegram",
                params={"telegram_id": telegram_id},
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        "_get_access_token_for_telegram: status=%s telegram_id=%s",
                        resp.status,
                        telegram_id,
                    )
                    return None
                data = await resp.json()
                return data.get("access_token")
    except Exception as e:
        logger.exception(
            "_get_access_token_for_telegram: exception for telegram_id=%s: %s",
            telegram_id,
            e,
        )
        return None


@router.callback_query(F.data == "view_photos")
async def view_photos_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    await state.clear()

    access_token = await _get_access_token_for_telegram(telegram_id)
    if not access_token:
        text = "😔 Не удалось получить токен для просмотра фото. Попробуйте позже."
        await callback.message.edit_text(
            text,
            reply_markup=back_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    data = await _fetch_photos_page(access_token=access_token, page=1, page_size=10)
    total = data.get("total", 0)

    if total == 0:
        text = (
            "🖼 <b>Просмотр фото</b>\n\n"
            "У вас пока нет загруженных фото."
        )
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    text = (
        "🖼 <b>Просмотр фото</b>\n\n"
        f"Сейчас у вас сохранено <b>{total}</b> фото.\n"
        "Выберите, какие из них показать."
    )

    await state.update_data(
        total_photos=total,
        access_token=access_token,
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="view_photos",
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=view_photos_keyboard(total),
    )
    await callback.answer()

@router.callback_query(F.data.regexp(r"^view_photos_page_\d+$"))
async def view_photos_page_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    match = re.match(r"view_photos_page_(\d+)", callback.data)
    page = int(match.group(1)) if match else 1

    data_state = await state.get_data()
    access_token = data_state.get("access_token")
    total = data_state.get("total_photos")

    if not access_token:
        access_token = await _get_access_token_for_telegram(telegram_id)
        if not access_token:
            text = "😔 Не удалось получить токен для просмотра фото. Попробуйте позже."
            await callback.message.edit_text(
                text,
                reply_markup=back_keyboard(),
            )
            await state.update_data(
                current_message_id=callback.message.message_id,
                current_text=text,
                current_keyboard="back",
            )
            await callback.answer()
            return
        await state.update_data(access_token=access_token)

    if total is None:
        resp = await _fetch_photos_page(
            access_token=access_token,
            page=1,
            page_size=1,
        )
        total = resp.get("total", 0)
        await state.update_data(total_photos=total)

    resp = await _fetch_photos_page(
        access_token=access_token,
        page=page,
        page_size=10,
    )
    items = resp.get("items", [])
    total = resp.get("total", total)

    old_ids = data_state.get("photo_message_ids", [])
    old_menu_id = data_state.get("menu_message_id")

    await _delete_photo_messages(callback.bot, callback.message.chat.id, old_ids)

    if old_menu_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=old_menu_id,
            )
        except Exception:
            pass

    new_ids = []

    if not items:
        text = (
            "🖼 <b>Просмотр фото</b>\n\n"
            f"В выбранном диапазоне у вас нет фото.\n"
            f"Всего сохранено: <b>{total}</b>."
        )

        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=view_photos_keyboard(total),
            )
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.warning("Не удалось обновить текст view_photos_page (нет фото): %s", e)

        await state.update_data(
            photo_message_ids=[],
            menu_message_id=None,
            total_photos=total,
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="view_photos",
        )
        await callback.answer()
        return

    for info in items:
        telegram_file_id = info.get("telegram_file_id")
        photo_id = info["id"]

        photo_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_photo_{photo_id}")],
        ])

        try:
            msg = await _send_photo_message_by_photo_info(
                callback=callback,
                info=info,
                photo_keyboard=photo_keyboard,
                access_token=access_token,
            )
            new_ids.append(msg.message_id)

        except Exception as e:
            logger.exception("Не удалось отправить фото photo_id=%s: %s", photo_id, e)

    if total <= 10 and page == 1:
        text = (
            "🖼 <b>Просмотр фото</b>\n\n"
            f"У вас сохранена <b>{total}</b> фотография."
            if total == 1
            else f"У вас сохранено <b>{total}</b> фотографии."
        )
    else:
        start = (page - 1) * 10 + 1
        end = min(page * 10, total)
        text = (
            "🖼 <b>Просмотр фото</b>\n\n"
            f"Показаны фото с <b>{start}</b> по <b>{end}</b>.\n"
            f"Всего сохранено: <b>{total}</b>."
        )

    menu_msg = await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=view_photos_keyboard(total),
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.update_data(
        photo_message_ids=new_ids,
        menu_message_id=menu_msg.message_id,
        total_photos=total,
        current_message_id=menu_msg.message_id,
        current_text=text,
        current_keyboard="view_photos",
    )

    await callback.answer()

@router.callback_query(F.data == "view_photos_latest")
async def view_photos_latest_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    data_state = await state.get_data()
    access_token = data_state.get("access_token")

    if not access_token:
        access_token = await _get_access_token_for_telegram(telegram_id)
        if not access_token:
            text = "😔 Не удалось получить токен для просмотра фото. Попробуйте позже."
            await callback.message.edit_text(
                text,
                reply_markup=back_keyboard(),
            )
            await state.update_data(
                current_message_id=callback.message.message_id,
                current_text=text,
                current_keyboard="back",
            )
            await callback.answer()
            return
        await state.update_data(access_token=access_token)

    resp = await _fetch_photos_page(
        access_token=access_token,
        page=1,
        page_size=10,
    )
    items = resp.get("items", [])
    total = resp.get("total", 0)

    old_ids = data_state.get("photo_message_ids", [])
    old_menu_id = data_state.get("menu_message_id")

    await _delete_photo_messages(callback.bot, callback.message.chat.id, old_ids)

    if old_menu_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=old_menu_id,
            )
        except Exception:
            pass

    new_ids: list[int] = []

    if total == 0 or not items:
        text = "🖼 <b>Просмотр фото</b>\n\n" "У вас пока нет загруженных фото."

        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=back_keyboard(),
            )
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.warning("Не удалось обновить текст view_photos_latest (0): %s", e)

        await state.update_data(
            photo_message_ids=[],
            menu_message_id=None,
            total_photos=0,
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    for info in items:
        telegram_file_id = info.get("telegram_file_id")
        photo_id = info["id"]

        photo_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_photo_{photo_id}")],
        ])

        try:
            msg = await _send_photo_message_by_photo_info(
                callback=callback,
                info=info,
                photo_keyboard=photo_keyboard,
                access_token=access_token,
            )
            new_ids.append(msg.message_id)

        except Exception as e:
            logger.exception("Не удалось отправить фото photo_id=%s: %s", photo_id, e)

    shown = len(items)
    if total == 1:
        text = (
            "🖼 <b>Последняя фотография</b>\n\n" "У вас сохранена <b>1</b> фотография."
        )
    elif total <= 10:
        text = (
            "🖼 <b>Последние фото</b>\n\n"
            f"У вас сохранено <b>{total}</b> фотографий.\n"
            "Я показал все из них."
        )
    else:
        text = (
            "🖼 <b>Последние 10 фото</b>\n\n"
            f"Всего сохранено: <b>{total}</b>.\n"
            f"Сейчас показаны <b>{shown}</b> самых новых."
        )

    menu_msg = await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=view_photos_keyboard(total),
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.update_data(
        photo_message_ids=new_ids,
        menu_message_id=menu_msg.message_id,
        total_photos=total,
        current_message_id=menu_msg.message_id,
        current_text=text,
        current_keyboard="view_photos",
    )

    await callback.answer()


@router.callback_query(F.data.regexp(r"^delete_photo_[a-f0-9\-]+$"))
async def delete_single_photo_callback(callback: CallbackQuery, state: FSMContext):
    """
    Удаляет одно фото из БД и чата
    """
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        await callback.answer("Сначала зарегистрируйтесь", show_alert=True)
        return

    photo_id = callback.data.replace("delete_photo_", "")

    async with SessionLocal() as session:
        result = await session.execute(
            sql_text(
                """
                UPDATE user_photos
                SET is_active = FALSE
                WHERE id = :photo_id
                  AND user_id = (
                      SELECT user_id
                      FROM telegram_accounts
                      WHERE telegram_id = :telegram_id
                  )
                RETURNING id
                """
            ),
            {"photo_id": photo_id, "telegram_id": telegram_id},
        )
        deleted_id = result.scalar_one_or_none()
        await session.commit()

    if not deleted_id:
        await callback.answer("Фото не найдено или уже удалено", show_alert=True)
        return

    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning("Не удалось удалить сообщение с фото: %s", e)

    data = await state.get_data()
    total_photos = data.get("total_photos", 0)
    if total_photos > 0:
        total_photos -= 1
        await state.update_data(total_photos=total_photos)

    menu_message_id = data.get("menu_message_id")
    if menu_message_id and total_photos >= 0:
        try:
            if total_photos == 0:
                new_text = "🖼 <b>Просмотр фото</b>\n\nУ вас пока нет загруженных фото."
                new_keyboard = back_keyboard()
            elif total_photos == 1:
                new_text = "🖼 <b>Последняя фотография</b>\n\nУ вас сохранена <b>1</b> фотография."
                new_keyboard = view_photos_keyboard(total_photos)
            else:
                new_text = (
                    "🖼 <b>Последние фото</b>\n\n"
                    f"У вас сохранено <b>{total_photos}</b> фотографий."
                )
                new_keyboard = view_photos_keyboard(total_photos)

            await callback.bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=menu_message_id,
                text=new_text,
                parse_mode="HTML",
                reply_markup=new_keyboard,
            )
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.warning("Не удалось обновить меню после удаления фото: %s", e)

    await callback.answer("🗑 Фото удалено")

# ============================================================
# Удаление всех фото
# ============================================================

@router.callback_query(F.data == "confirm_delete_all_photos")
async def confirm_delete_all_photos_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    access_token = await _get_access_token_for_telegram(telegram_id)
    if not access_token:
        text = "😔 Не удалось получить токен. Попробуйте позже."
        await callback.message.edit_text(
            text,
            reply_markup=back_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get(
            f"{API_BASE_URL}/photos?page=1&page_size=1",
            headers=headers,
        ) as resp:
            if resp.status != 200:
                total = 0
            else:
                data = await resp.json()
                total = data.get("total", 0)

    if total == 0:
        text = "У вас пока нет загруженных фото."
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    text = (
        f"⚠️ <b>Удаление всех фото</b>\n\n"
        f"У вас сохранено <b>{total}</b> фото.\n"
        f"Вы уверены, что хотите удалить их все?\n\n"
        f"Это действие <b>необратимо</b>."
    )

    await state.update_data(
        access_token=access_token,
        total_photos=total,
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="confirm_delete_all_photos",
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=confirm_delete_photos_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "delete_all_photos_confirmed")
async def delete_all_photos_confirmed_callback(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    data = await state.get_data()
    access_token = data.get("access_token")

    if not access_token:
        access_token = await _get_access_token_for_telegram(telegram_id)
        if not access_token:
            text = "😔 Не удалось получить токен. Попробуйте позже."
            await callback.message.edit_text(
                text,
                reply_markup=back_keyboard(),
            )
            await state.update_data(
                current_message_id=callback.message.message_id,
                current_text=text,
                current_keyboard="back",
            )
            await callback.answer()
            return

    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {access_token}"}
            async with session.delete(
                f"{API_BASE_URL}/photos/all",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        "delete_all_photos: status=%s telegram_id=%s",
                        resp.status,
                        telegram_id,
                    )
                    error_data = await resp.json() if resp.content_type == 'application/json' else {}
                    error_msg = error_data.get('detail', 'Неизвестная ошибка')
                    
                    text = f"😔 Не удалось удалить фото.\n\nОшибка: {error_msg}"
                    await callback.message.edit_text(
                        text,
                        parse_mode="HTML",
                        reply_markup=back_keyboard(),
                    )
                    await state.update_data(
                        current_message_id=callback.message.message_id,
                        current_text=text,
                        current_keyboard="back",
                    )
                    await callback.answer()
                    return
    except Exception as e:
        logger.exception("delete_all_photos: exception: %s", e)
        text = "😔 Не удалось связаться с сервером. Попробуйте позже"
        await callback.message.edit_text(
            text,
            reply_markup=back_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    photo_message_ids = data.get("photo_message_ids", [])
    for mid in photo_message_ids:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=mid,
            )
            await asyncio.sleep(0.05)
        except Exception:
            pass

    text = (
        "✅ <b>Все фото удалены</b>\n\n"
        "Теперь ваш гардероб пуст."
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )

    await state.update_data(
        photo_message_ids=[],
        menu_message_id=None,
        total_photos=0,
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="back",
    )

    await callback.answer()


@router.callback_query(F.data == "cancel_delete_all_photos")
async def cancel_delete_all_photos_callback(callback: CallbackQuery, state: FSMContext):
    """Отменить удаление всех фото - вернуться к просмотру"""
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    data = await state.get_data()
    total = data.get("total_photos", 0)

    if total == 0:
        text = "У вас пока нет загруженных фото."
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    text = (
        "🖼 <b>Просмотр фото</b>\n\n"
        f"Сейчас у вас сохранено <b>{total}</b> фото.\n"
        "Выберите, какие из них показать."
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=view_photos_keyboard(total),
    )

    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=text,
        current_keyboard="view_photos",
    )

    await callback.answer()

# ============================================================
# Рекомендации, сбор образа
# ============================================================


def _fashion_mode_title(mode: str) -> str:
    return "🧥 Собрать образ" if mode == "outfit" else "👗 Рекомендации по одежде"


def _fashion_mode_intro(mode: str, total: int) -> str:
    if mode == "outfit":
        return (
            "🧥 <b>Собрать образ</b>\n\n"
            "Выберите фото вещи или готового образа.\n"
            "Я предложу конкретный комплект: что добавить, какую обувь и аксессуар выбрать.\n\n"
            f"В гардеробе сейчас <b>{total}</b> фото."
        )

    return (
        "👗 <b>Получить рекомендации</b>\n\n"
        "Выберите фото, и я подскажу, как улучшить образ: "
        "цветовой акцент, обувь, сумку, слой или аксессуар.\n\n"
        f"В гардеробе сейчас <b>{total}</b> фото."
    )


def _mode_to_task_mode(mode: str) -> str:
    return "outfit" if mode == "outfit" else "recommendation"


def _model_label(model_code: str) -> str:
    return "ResNet" if model_code == "resnet" else "RandomForest"


def _fashion_processing_text(mode: str, model_type: str) -> str:
    if mode == "outfit":
        return (
            "🧥 <b>Сбор образа</b>\n\n"
            f"⏳ Собираю образ через <b>{model_type}</b>.\n"
            "Это может занять несколько секунд.\n\n"
            "Вы можете выйти из раздела — я пришлю готовый образ, когда он будет готов."
        )

    return (
        "👗 <b>Рекомендации по одежде</b>\n\n"
        f"⏳ Анализирую фото через <b>{model_type}</b>.\n"
        "Это может занять несколько секунд.\n\n"
        "Вы можете выйти из раздела — я пришлю готовые рекомендации, когда они будут готовы."
    )

def _main_menu_text(notice: str | None = None) -> str:
    if notice:
        return (
            "🏠 <b>Главное меню Fashion Bot!</b>\n\n"
            f"{notice.strip()}\n\n"
            "Я помогаю управлять <b>персональным гардеробом и стилем</b>.\n"
            "Выберите нужное действие ниже."
        )

    return (
        "🏠 <b>Главное меню Fashion Bot!</b>\n\n"
        "Я помогаю управлять <b>персональным гардеробом и стилем</b>.\n"
        "Выберите нужное действие ниже."
    )


def _fashion_done_menu_text(mode: str) -> str:
    return (
        "🏠 <b>Главное меню Fashion Bot!</b>\n\n"
        "Результат можно увидеть выше и в истории веб-версии.\n\n"
        "Выберите нужное действие ниже."
    )


def _fashion_failed_menu_text(mode: str, error_text: str | None = None) -> str:
    if error_text:
        cleaned = str(error_text).strip()
        notice = f"😔 {cleaned}"
    else:
        action = "собрать образ" if mode == "outfit" else "подготовить рекомендацию"
        notice = f"😔 Не удалось {action}."

    return (
        "🏠 <b>Главное меню Fashion Bot!</b>\n\n"
        f"{notice}\n\n"
        "Я помогаю управлять <b>персональным гардеробом и стилем</b>.\n"
        "Выберите нужное действие ниже."
    )


async def _get_model_task_result(task_id: str) -> dict | None:
    async with SessionLocal() as session:
        result = await session.execute(
            sql_text(
                """
                SELECT status, result
                FROM model_tasks
                WHERE task_id = :task_id
                LIMIT 1
                """
            ),
            {"task_id": task_id},
        )
        row = result.mappings().first()

    if not row:
        return None

    payload = None
    if row["result"]:
        try:
            payload = json.loads(row["result"])
        except Exception:
            payload = {"text": str(row["result"])}

    return {"status": row["status"], "result": payload}


async def _create_model_task(user_id: str, photo_id: str, mode: str, model_type: str) -> str:
    task_id = str(uuid4())
    initial_result = {
        "mode": mode,
        "model_type": model_type,
        "photo_id": photo_id,
        "message": "Задача поставлена в очередь",
    }
    async with SessionLocal() as session:
        await session.execute(
            sql_text(
                """
                INSERT INTO model_tasks (task_id, user_id, status, result)
                VALUES (:task_id, :user_id, :status, :result)
                """
            ),
            {
                "task_id": task_id,
                "user_id": user_id,
                "status": "PENDING",
                "result": json.dumps(initial_result, ensure_ascii=False),
            },
        )
        await session.commit()
    return task_id


async def _open_fashion_action_menu(
    callback: CallbackQuery,
    state: FSMContext,
    mode: str,
    *,
    send_new: bool = False,
):
    telegram_id = callback.from_user.id

    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(
            text,
            reply_markup=start_keyboard(is_registered=False),
        )
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="start",
        )
        await callback.answer()
        return

    await state.clear()

    access_token = await _get_access_token_for_telegram(telegram_id)
    if not access_token:
        text = "😔 Не удалось получить токен для работы с гардеробом. Попробуйте позже."
        await callback.message.edit_text(text, reply_markup=back_keyboard())
        await state.update_data(
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="back",
        )
        await callback.answer()
        return

    data = await _fetch_photos_page(access_token=access_token, page=1, page_size=1)
    total = data.get("total", 0)
    text = _fashion_mode_intro(mode, total)

    keyboard = fashion_action_menu_keyboard(mode, total)

    if send_new:
        msg = await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        message_id = msg.message_id
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        message_id = callback.message.message_id

    await state.update_data(
        access_token=access_token,
        total_photos=total,
        fashion_mode=mode,
        current_message_id=message_id,
        current_text=text,
        current_keyboard="fashion_action",
    )
    await callback.answer()


@router.callback_query(F.data == "get_recommendations")
async def get_recommendations_callback(callback: CallbackQuery, state: FSMContext):
    await _open_fashion_action_menu(callback, state, "rec")


@router.callback_query(F.data == "build_outfit")
async def build_outfit_callback(callback: CallbackQuery, state: FSMContext):
    await _open_fashion_action_menu(callback, state, "outfit")


@router.callback_query(F.data.regexp(r"^fa_new:(rec|outfit)$"))
async def fashion_action_new_callback(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    mode = parts[1] if len(parts) > 1 else "rec"
    await _open_fashion_action_menu(callback, state, mode, send_new=True)


@router.callback_query(F.data.regexp(r"^fa_back:(rec|outfit)$"))
async def fashion_action_back_to_menu_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_photo_message_id = data.get("selected_fashion_photo_message_id")
    if selected_photo_message_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, selected_photo_message_id)
        except Exception:
            pass
    parts = callback.data.split(":")
    mode = parts[1] if len(parts) > 1 else data.get("fashion_mode", "rec")
    await _open_fashion_action_menu(callback, state, mode)


async def _show_fashion_photos_page(
    callback: CallbackQuery,
    state: FSMContext,
    mode: str,
    page: int,
    *,
    latest: bool = False,
):
    telegram_id = callback.from_user.id
    if not await is_user_registered(telegram_id):
        text = "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться»."
        await callback.message.edit_text(text, reply_markup=start_keyboard(is_registered=False))
        await state.update_data(current_message_id=callback.message.message_id, current_text=text, current_keyboard="start")
        await callback.answer()
        return

    data_state = await state.get_data()
    access_token = data_state.get("access_token")
    if not access_token:
        access_token = await _get_access_token_for_telegram(telegram_id)
        if not access_token:
            text = "😔 Не удалось получить токен для просмотра фото. Попробуйте позже."
            await callback.message.edit_text(text, reply_markup=back_keyboard())
            await state.update_data(current_message_id=callback.message.message_id, current_text=text, current_keyboard="back")
            await callback.answer()
            return
        await state.update_data(access_token=access_token)

    resp = await _fetch_photos_page(access_token=access_token, page=page, page_size=10)
    items = resp.get("items", [])
    total = resp.get("total", 0)

    old_ids = data_state.get("photo_message_ids", [])
    old_menu_id = data_state.get("menu_message_id")
    await _delete_photo_messages(callback.bot, callback.message.chat.id, old_ids)
    if old_menu_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, old_menu_id)
        except Exception:
            pass

    if not items:
        text = (
            f"{_fashion_mode_title(mode)}\n\n"
            "В выбранном диапазоне нет фото. Загрузите фото или выберите другой диапазон."
        )
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=fashion_action_menu_keyboard(mode, total),
        )
        await state.update_data(
            photo_message_ids=[],
            menu_message_id=None,
            total_photos=total,
            fashion_mode=mode,
            current_message_id=callback.message.message_id,
            current_text=text,
            current_keyboard="fashion_action",
        )
        await callback.answer()
        return

    new_ids: list[int] = []
    for info in items:
        telegram_file_id = info.get("telegram_file_id")
        photo_id = info["id"]
        keyboard = choose_photo_for_action_keyboard(mode, photo_id)

        try:
            msg = await _send_photo_message_by_photo_info(
                callback=callback,
                info=info,
                photo_keyboard=keyboard,
                access_token=access_token,
            )
            new_ids.append(msg.message_id)
        except Exception as e:
            logger.exception("Не удалось отправить фото для %s photo_id=%s: %s", mode, photo_id, e)

    if latest:
        text = f"{_fashion_mode_title(mode)}\n\nПоказаны последние фото. Выберите одно фото для анализа."
    else:
        start = (page - 1) * 10 + 1
        end = min(page * 10, total)
        text = f"{_fashion_mode_title(mode)}\n\nПоказаны фото с <b>{start}</b> по <b>{end}</b>. Выберите одно фото для анализа."

    menu_msg = await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=fashion_action_menu_keyboard(mode, total),
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.update_data(
        photo_message_ids=new_ids,
        menu_message_id=menu_msg.message_id,
        total_photos=total,
        fashion_mode=mode,
        current_message_id=menu_msg.message_id,
        current_text=text,
        current_keyboard="fashion_action",
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^fa_page:(rec|outfit):\d+$"))
async def fashion_action_page_callback(callback: CallbackQuery, state: FSMContext):
    _, mode, page_raw = callback.data.split(":", 2)
    await _show_fashion_photos_page(callback, state, mode, int(page_raw))


@router.callback_query(F.data.regexp(r"^fa_latest:(rec|outfit)$"))
async def fashion_action_latest_callback(callback: CallbackQuery, state: FSMContext):
    _, mode = callback.data.split(":", 1)
    await _show_fashion_photos_page(callback, state, mode, 1, latest=True)


@router.callback_query(F.data.regexp(r"^fs:(rec|outfit):[a-f0-9\-]+$"))
async def fashion_select_photo_callback(callback: CallbackQuery, state: FSMContext):
    _, mode, photo_id = callback.data.split(":", 2)
    data = await state.get_data()
    old_ids = data.get("photo_message_ids", [])
    old_menu_id = data.get("menu_message_id")

    selected_message_id = callback.message.message_id
    for mid in old_ids:
        if mid == selected_message_id:
            continue
        try:
            await callback.bot.delete_message(callback.message.chat.id, mid)
        except Exception:
            pass

    if old_menu_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, old_menu_id)
        except Exception:
            pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    text = (
        f"{_fashion_mode_title(mode)}\n\n"
        "Фото выбрано. Теперь выберите модель анализа.\n\n"
        "🌲 <b>RandomForest</b> — быстрее, хорошо подходит для первой проверки.\n"
        "🧠 <b>ResNet</b> — глубже, но может работать дольше."
    )
    model_msg = await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=choose_model_keyboard(mode, photo_id),
    )

    await state.update_data(
        photo_message_ids=[],
        menu_message_id=None,
        selected_fashion_photo_id=photo_id,
        selected_fashion_photo_message_id=selected_message_id,
        current_message_id=model_msg.message_id,
        current_text=text,
        current_keyboard="fashion_model",
        fashion_mode=mode,
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^fa:(rec|outfit):(rf|resnet):[a-f0-9\-]+$"))
async def fashion_choose_model_callback(callback: CallbackQuery, state: FSMContext):
    _, mode, model_code, photo_id = callback.data.split(":", 3)
    telegram_id = callback.from_user.id

    user_id = await get_user_id_by_telegram(telegram_id)
    if not user_id:
        await callback.answer("Сначала зарегистрируйтесь", show_alert=True)
        return

    model_type = _model_label(model_code)
    task_mode = _mode_to_task_mode(mode)
    task_id = await _create_model_task(str(user_id), photo_id, task_mode, model_type)

    try:
        from app.worker.celery_app import celery_app
        celery_app.send_task(
            "app.worker.tasks.analyze_fashion_photo_task",
            args=[task_id, str(user_id), photo_id, task_mode, model_type],
        )
    except Exception as e:
        logger.exception("Не удалось поставить ML-задачу в очередь: %s", e)
        await callback.message.edit_text(
            "😔 Не удалось поставить задачу в очередь. Проверьте Redis/Celery worker.",
            reply_markup=fashion_action_result_keyboard(mode),
        )
        await callback.answer()
        return

    processing_text = _fashion_processing_text(mode, model_type)
    await callback.message.edit_text(
        processing_text,
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
    await state.update_data(
        current_message_id=callback.message.message_id,
        current_text=processing_text,
        current_keyboard="back",
        fashion_mode=mode,
        selected_fashion_photo_id=photo_id,
    )
    await callback.answer("Фото принято в работу")

    selected_photo_message_id = (await state.get_data()).get("selected_fashion_photo_message_id")
    asyncio.create_task(
        _wait_and_deliver_fashion_result(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            user_id=str(user_id),
            task_id=task_id,
            mode=mode,
            model_type=model_type,
            photo_id=photo_id,
            processing_message_id=callback.message.message_id,
            selected_photo_message_id=selected_photo_message_id,
        )
    )


async def _wait_and_deliver_fashion_result(
    *,
    bot,
    chat_id: int,
    user_id: str,
    task_id: str,
    mode: str,
    model_type: str,
    photo_id: str,
    processing_message_id: int | None,
    selected_photo_message_id: int | None,
):
    result_payload = None
    status = None

    for _ in range(90):  # up to ~3 minutes
        await asyncio.sleep(2)
        task_row = await _get_model_task_result(task_id)
        if not task_row:
            continue
        status = task_row.get("status")
        result_payload = task_row.get("result")
        if status in {"SUCCESS", "FAILURE"}:
            break

    is_success = bool(result_payload and result_payload.get("ok") and status == "SUCCESS")

    if is_success:
        # Успешный сценарий: выбранное фото оставляем в чате,
        # сообщение "анализирую" перезаписываем на готовый ответ,
        # ниже отправляем стандартное главное меню.
        result_text = result_payload.get("text") or "✅ Рекомендация готова."

        edited_result = False
        if processing_message_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message_id,
                    text=result_text,
                    parse_mode="HTML",
                    reply_markup=None,
                )
                edited_result = True
            except Exception as e:
                logger.warning("Не удалось перезаписать processing_message_id=%s результатом: %s", processing_message_id, e)

        if not edited_result:
            try:
                await bot.send_message(chat_id, result_text, parse_mode="HTML")
            except Exception as e:
                logger.exception("Не удалось отправить текст результата task_id=%s: %s", task_id, e)

        await bot.send_message(
            chat_id,
            _fashion_done_menu_text(mode),
            parse_mode="HTML",
            reply_markup=start_keyboard(is_registered=True),
        )
        return

    # Ошибка/таймаут: выбранное фото убираем, а сообщение "анализирую"
    # перезаписываем в главное меню с причиной. Новое сообщение не отправляем.
    if selected_photo_message_id:
        try:
            await bot.delete_message(chat_id, selected_photo_message_id)
        except Exception:
            pass

    error_text = None
    if result_payload:
        error_text = (
            result_payload.get("text")
            or result_payload.get("message")
            or result_payload.get("error")
        )
    if not error_text:
        error_text = "Время ожидания результата истекло. Попробуйте выбрать фото ещё раз."

    menu_text = _fashion_failed_menu_text(mode, error_text)

    if processing_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message_id,
                text=menu_text,
                parse_mode="HTML",
                reply_markup=start_keyboard(is_registered=True),
            )
            return
        except Exception as e:
            logger.warning("Не удалось перезаписать processing_message_id=%s ошибкой: %s", processing_message_id, e)

    await bot.send_message(
        chat_id,
        menu_text,
        parse_mode="HTML",
        reply_markup=start_keyboard(is_registered=True),
    )


# ============================================================
# Обработчик неожиданных сообщений
# ============================================================

@router.message()
async def unexpected_message_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state is not None:
        return

    try:
        await message.delete()
    except Exception:
        pass

    is_registered = await is_user_registered(message.from_user.id)
    data = await state.get_data()

    current_message_id = data.get("current_message_id")
    current_text = data.get("current_text")
    current_keyboard = data.get("current_keyboard")

    if not current_message_id or not current_text or not current_keyboard:
        warning_text = (
            "🥺 <b>Извините, но сейчас я ожидаю нажатие кнопок.</b>\n"
            "Пожалуйста, выберите нужное действие ниже."
        )
        sent_message = await message.answer(
            warning_text,
            parse_mode="HTML",
            reply_markup=start_keyboard(is_registered=is_registered),
        )
        await state.update_data(
            current_message_id=sent_message.message_id,
            current_text=warning_text,
            current_keyboard="start",
        )
        return
    
    new_text = insert_warning_into_text(current_text)

    if current_keyboard == "start":
        keyboard = start_keyboard(is_registered=is_registered)
    elif current_keyboard == "back":
        keyboard = back_keyboard()
    elif current_keyboard == "back_to_link_web":
        keyboard = back_to_link_web_keyboard()
    elif current_keyboard == "profile":
        row = await get_profile_row(message.from_user.id)
        keyboard = profile_keyboard(has_last_name=has_last_name(row))
    elif current_keyboard == "cancel":
        keyboard = cancel_input_keyboard()
    elif current_keyboard == "link_web":
        keyboard = link_web_keyboard()
    elif current_keyboard == "link_from_web":
        keyboard = link_from_web_keyboard()
    elif current_keyboard == "view_photos":
        total_photos = data.get("total_photos", 0)
        keyboard = view_photos_keyboard(total_photos) if total_photos > 0 else back_keyboard()
    elif current_keyboard == "confirm_delete_all_photos":
        keyboard = confirm_delete_photos_keyboard()
    elif current_keyboard == "account_management":
        keyboard = account_management_keyboard()
    elif current_keyboard == "confirm_unlink":
        keyboard = confirm_unlink_telegram_keyboard()
    elif current_keyboard == "confirm_delete_account":
        keyboard = confirm_delete_account_keyboard()
    elif current_keyboard == "fashion_action":
        mode = data.get("fashion_mode", "rec")
        total_photos = data.get("total_photos", 0)
        keyboard = fashion_action_menu_keyboard(mode, total_photos)
    elif current_keyboard == "fashion_model":
        mode = data.get("fashion_mode", "rec")
        photo_id = data.get("selected_fashion_photo_id", "")
        keyboard = choose_model_keyboard(mode, photo_id) if photo_id else back_keyboard()
    elif current_keyboard == "fashion_result":
        mode = data.get("fashion_mode", "rec")
        keyboard = fashion_action_result_keyboard(mode)
    else:
        keyboard = start_keyboard(is_registered=is_registered)

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=current_message_id,
            text=new_text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logger.warning("Не удалось обновить сообщение в unexpected_message_handler: %s", e)