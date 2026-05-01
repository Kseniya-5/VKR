from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def start_keyboard(is_registered: bool) -> InlineKeyboardMarkup:
    buttons = []

    if not is_registered:
        buttons.append(
            [
                InlineKeyboardButton(text="📝 Зарегистрироваться", callback_data="start_register")
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(text="❔ Помощь", callback_data="open_help")
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(text="❔ Помощь", callback_data="open_help"),
                InlineKeyboardButton(text="⚙️ Управление аккаунтом", callback_data="account_management")
            ]
        )

        buttons.append(
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="open_profile"),
                InlineKeyboardButton(text="🔗 Связать с веб-версией", callback_data="link_web")
            ]
        )

        buttons.append(
            [
                InlineKeyboardButton(text="📸 Загрузить фото", callback_data="upload_photo"),
                InlineKeyboardButton(text="🖼 Посмотреть фото", callback_data="view_photos")
            ]
        )

        buttons.append(
            [
                InlineKeyboardButton(text="👗 Получить рекомендации", callback_data="get_recommendations"),
                InlineKeyboardButton(text="🧥 Собрать образ", callback_data="build_outfit")
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            ]
        ]
    )


def account_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔌 Отвязать Telegram", callback_data="unlink_tg"),
                InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data="delete_me"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            ],
        ]
    )


def confirm_action_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
                InlineKeyboardButton(text="❌ Нет", callback_data="back_account_management"),
            ]
        ]
    )


def profile_keyboard(has_last_name: bool) -> InlineKeyboardMarkup:
    last_name_button_text = "✏️ Обновить фамилию" if has_last_name else "✏️ Добавить фамилию"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✍️ Обновить имя", callback_data="edit_first_name"),
                InlineKeyboardButton(text=last_name_button_text, callback_data="edit_last_name")
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            ],
        ]
    )

def cancel_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_profile_edit")
            ]
        ]
    )