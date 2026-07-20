from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from utils import get_link

def main_menu():
    """Главное меню - инлайн кнопки"""
    buttons = [
        [
            InlineKeyboardButton(text="💬 Чат", callback_data="link_chat"),
            InlineKeyboardButton(text="📢 Новости", callback_data="link_news")
        ],
        [
            InlineKeyboardButton(text="🛟 Резерв", callback_data="link_reserve"),
            InlineKeyboardButton(text="🤖 Бот", url=get_link("bot"))
        ],
        [
            InlineKeyboardButton(text="👨‍💼 CEO", url=get_link("ceo")),
            InlineKeyboardButton(text="🎧 Оператор", url=get_link("operator"))
        ],
        [
            InlineKeyboardButton(text="✉️ Связаться с оператором", callback_data="support")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cancel_inline():
    """Кнопка отмены - инлайн"""
    buttons = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_support")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_panel():
    """Админ-панель (Reply)"""
    buttons = [
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔗 Изменить ссылки")],
        [KeyboardButton(text="👨‍💻 Изменить операторов")],
        [KeyboardButton(text="◀️ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)