from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.bot.states import ProfileEditState
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.bot.keyboards import (
    start_keyboard,
    back_keyboard,
    profile_keyboard,
    cancel_input_keyboard,
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


async def is_user_registered(telegram_id: int) -> bool:
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
        return result.scalar_one_or_none() is not None


async def get_profile_row(telegram_id: int):
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

################################################################################

def get_help_text() -> str:
    return (
        "❔ <b>Помощь</b>\n\n"
        "Fashion Bot помогает управлять персональным гардеробом и стилем.\n\n"
        "<b>Основные функции:</b>\n"
        "• 👤 Профиль — просмотр данных аккаунта\n"
        "• ⚙️ Управление аккаунтом — отвязка Telegram или удаление аккаунта\n"
        "• 🔗 Веб-версия — связь с сайтом\n"
        "• 📸 Загрузить фото — отправка фото одежды\n"
        "• 🖼 Посмотреть фото — просмотр загруженных фото\n"
        "• 👗 Получить рекомендации — советы по подбору одежды\n"
        "• 🧥 Собрать образ — помощь в составлении комплекта"
        
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    telegram_id = message.from_user.id
    is_registered = await is_user_registered(telegram_id)

    if is_registered:
        text_value = (
            "👋 <b>С возвращением в Fashion Bot!</b>\n\n"
            "Я помогаю управлять <b>персональным гардеробом и стилем</b>.\n"
            "Выберите нужное действие ниже."
        )
    else:
        text_value = (
            "👗 <b>Добро пожаловать в Fashion Bot!</b>\n\n"
            "Я помогаю управлять <b>персональным гардеробом и стилем</b>.\n"
            "Чтобы начать, нажмите кнопку <b>«📝 Зарегистрироваться»</b>."
        )

    await message.answer(
        text_value,
        parse_mode="HTML",
        reply_markup=start_keyboard(is_registered=is_registered),
    )

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    is_registered = await is_user_registered(telegram_id)

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

    await callback.message.edit_text(
        text_value,
        parse_mode="HTML",
        reply_markup=start_keyboard(is_registered=is_registered),
    )
    await callback.answer()
################################################################################

@router.message(Command("help"))
async def help_cmd(message: Message):
    telegram_id = message.from_user.id
    is_registered = await is_user_registered(telegram_id)

    await message.answer(
        get_help_text(),
        parse_mode="HTML",
        reply_markup=back_keyboard() if is_registered else start_keyboard(is_registered=False),
    )

################################################################################

@router.callback_query(F.data == "start_register")
async def start_register_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

    if await is_user_registered(telegram_id):
        await callback.message.edit_text(
            "✅ Ваш Telegram уже зарегистрирован и привязан к аккаунту.",
            reply_markup=start_keyboard(is_registered=True),
        )
        await callback.answer()
        return

    async with SessionLocal() as session:
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

    await callback.message.edit_text(
        "✅ <b>Регистрация выполнена успешно!</b>\n\n"
        "Telegram сохранён и привязан к вашему аккаунту.\n"
        "Теперь вы можете пользоваться функциями бота.",
        parse_mode="HTML",
        reply_markup=start_keyboard(is_registered=True),
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
        await callback.message.edit_text(
            "Профиль ещё не создан.\n"
            "Сначала нажмите кнопку «📝 Зарегистрироваться».",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        profile_text,
        parse_mode="HTML",
        reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
    )
    await callback.answer()

@router.callback_query(F.data == "edit_last_name")
async def edit_last_name_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEditState.waiting_for_last_name)

    await callback.message.edit_text(
        "✏️ <b>Редактирование фамилии</b>\n\n"
        "Введите фамилию следующим сообщением.",
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
        await callback.message.edit_text(
            "Профиль ещё не создан.",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        profile_text,
        parse_mode="HTML",
        reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
    )
    await callback.answer("Редактирование отменено")


@router.message(ProfileEditState.waiting_for_last_name)
async def process_last_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введите фамилию текстом.")
        return

    telegram_id = message.from_user.id
    last_name = message.text.strip()

    async with SessionLocal() as session:
        await session.execute(
            text(
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

    await message.answer(
        "✅ Фамилия обновлена\n\n" + profile_text,
        parse_mode="HTML",
        reply_markup=profile_keyboard(has_last_name=has_last_name(row)),
    )

################################################################################

@router.callback_query(F.data == "open_help")
async def open_help_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        get_help_text(),
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "link_web")
async def link_web_callback(callback: CallbackQuery):
    if not await is_user_registered(callback.from_user.id):
        await callback.message.edit_text(
            "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться».",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "🔗 <b>Связь с веб-версией</b>\n\n"
        "Этот раздел можно использовать для привязки аккаунта к веб-версии.\n"
        "Сейчас функция находится в разработке.",
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "upload_photo")
async def upload_photo_callback(callback: CallbackQuery):
    if not await is_user_registered(callback.from_user.id):
        await callback.message.edit_text(
            "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться».",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📸 <b>Загрузка фото</b>\n\n"
        "Отправьте фотографию следующим сообщением.\n"
        "После этого бот сможет сохранить её и использовать для рекомендаций.",
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "view_photos")
async def view_photos_callback(callback: CallbackQuery):
    if not await is_user_registered(callback.from_user.id):
        await callback.message.edit_text(
            "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться».",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "🖼 <b>Посмотреть фото</b>\n\n"
        "Здесь будет список ваших загруженных фотографий.\n"
        "Сейчас функция находится в разработке.",
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "get_recommendations")
async def get_recommendations_callback(callback: CallbackQuery):
    if not await is_user_registered(callback.from_user.id):
        await callback.message.edit_text(
            "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться».",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "👗 <b>Рекомендации по одежде</b>\n\n"
        "Здесь будут рекомендации на основе ваших вещей, фото и предпочтений.\n"
        "Сейчас функция находится в разработке.",
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "build_outfit")
async def build_outfit_callback(callback: CallbackQuery):
    if not await is_user_registered(callback.from_user.id):
        await callback.message.edit_text(
            "Сначала нужно зарегистрироваться через кнопку «📝 Зарегистрироваться».",
            reply_markup=start_keyboard(is_registered=False),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "🧥 <b>Собрать образ</b>\n\n"
        "Здесь бот будет помогать составлять готовый комплект одежды.\n"
        "Сейчас функция находится в разработке.",
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
    await callback.answer()

################################################################################

