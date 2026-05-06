from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.bot.states import ProfileEditState, LinkWebState, UploadPhotosState, DeletePhotosState
from app.core.security import create_access_token
from sqlalchemy import text as sql_text 
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import aiohttp
import asyncio
from aiogram import Bot
import logging
import json
import re


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
API_BASE_URL = "http://fashion-api-service:8000"


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
                "👋 <b>С возвращением в Fashion Bot!</b>\n\n"
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
            "👋 <b>С возвращением в Fashion Bot!</b>\n\n"
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

    web_base_url = "http://127.0.0.1"
    link_url = f"{web_base_url}/from-telegram?token={access_token}"

    text = (
        "🔗 <b>Ссылка для входа в веб-версию</b>\n\n"
        "Нажмите на ссылку ниже, чтобы открыть веб-версию и "
        "создать веб-аккаунт, привязанный к вашему Telegram.\n\n"
        f"{link_url}"
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
        "Варианты:\n"
        "1. Нажмите «🔑 Сгенерировать ссылку для входа в веб» — "
        "бот создаст личную ссылку, по которой вы сможете зайти в веб-версию, "
        "привязанную к вашему Telegram.\n"
        "2. Или откройте веб-версию по ссылке ниже и используйте сценарий "
        "«сначала веб → потом ТГ по коду». Для этого нужно будет сначала удалить ТГ-аккаунт и получить код до регистрации."
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
        "Отправьте одно или несколько фотографий подряд.\n"
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
            "Отправьте одно или несколько фотографий подряд.\n"
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

        if telegram_file_id:
            msg = await callback.message.answer_photo(
                photo=telegram_file_id,
                reply_markup=photo_keyboard,
            )
        else:
            url = info["url"]
            msg = await callback.message.answer_photo(
                photo=url,
                reply_markup=photo_keyboard,
            )
        new_ids.append(msg.message_id)

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

        if telegram_file_id:
            msg = await callback.message.answer_photo(
                photo=telegram_file_id,
                reply_markup=photo_keyboard,
            )
        else:
            url = info["url"]
            msg = await callback.message.answer_photo(
                photo=url,
                reply_markup=photo_keyboard,
            )
        new_ids.append(msg.message_id)

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

@router.callback_query(F.data == "get_recommendations")
async def get_recommendations_callback(callback: CallbackQuery, state: FSMContext):
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

    text = (
        "👗 <b>Рекомендации по одежде</b>\n\n"
        "Здесь будут рекомендации на основе ваших вещей, фото и предпочтений.\n"
        "Сейчас функция находится в разработке."
    )

    await state.update_data(
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


@router.callback_query(F.data == "build_outfit")
async def build_outfit_callback(callback: CallbackQuery, state: FSMContext):
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

    text = (
        "🧥 <b>Собрать образ</b>\n\n"
        "Здесь бот будет помогать составлять готовый комплект одежды.\n"
        "Сейчас функция находится в разработке."
    )

    await state.update_data(
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