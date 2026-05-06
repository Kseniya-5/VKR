from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

WEB_BASE_URL = "https://speech-nest-output-legs.trycloudflare.com"

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
                InlineKeyboardButton(text="🔑 Войти по коду из веб-версии", callback_data="start_link_from_web")
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


def link_from_web_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌐 Открыть веб-версию", url=WEB_BASE_URL)
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            ],
        ]
    )


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
                InlineKeyboardButton(text="🔌 Отвязать Telegram", callback_data="confirm_unlink_telegram"),
                InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data="confirm_delete_account"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            ],
        ]
    )


def confirm_unlink_telegram_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, отвязать", callback_data="do_unlink_telegram"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="account_management"),
            ]
        ]
    )


def confirm_delete_account_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data="do_delete_account"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="account_management"),
            ]
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


def back_to_link_web_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="link_web")
            ]
        ]
    )


def link_web_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔑 Сгенерировать ссылку для входа в веб", callback_data="generate_web_link")
            ],
            [
                InlineKeyboardButton(text="🌐 Открыть веб-версию", url=WEB_BASE_URL)
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            ],
        ]
    )


def view_photos_keyboard(total_photos: int) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []

    pages = (total_photos + 9) // 10
    pages = max(1, min(pages, 10))

    for page in range(1, pages + 1):
        start = (page - 1) * 10 + 1
        end = min(page * 10, total_photos)
        buttons.append(
            [
                InlineKeyboardButton(text=f"📷 {start}–{end}", callback_data=f"view_photos_page_{page}")
            ]
        )

    if total_photos > 10:
        buttons.append(
            [
                InlineKeyboardButton(text="📷 Последние 10", callback_data="view_photos_latest")
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(text="🗑 Удалить все фото", callback_data="confirm_delete_all_photos")
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_delete_photos_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить все", callback_data="delete_all_photos_confirmed"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete_all_photos"),
            ]
        ]
    )