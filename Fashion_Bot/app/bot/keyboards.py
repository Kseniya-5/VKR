from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🔗 Аккаунты")],
        [KeyboardButton(text="📸 Загрузить фото"), KeyboardButton(text="🗑 Удалить данные")],
    ],
    resize_keyboard=True
)