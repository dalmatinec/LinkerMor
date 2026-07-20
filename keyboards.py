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
            InlineKeyboardButton(text="🤖 Бот", callback_data="link_bot")
        ],
        [
            InlineKeyboardButton(text="🌐 Сайт", callback_data="link_website")
        ],
        [
            InlineKeyboardButton(text="👨‍💼 CEO", callback_data="link_ceo"),
            InlineKeyboardButton(text="🎧 Оператор", callback_data="link_operator")
        ],
        [
            InlineKeyboardButton(text="✉️ Связаться с оператором", callback_data="support")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cancel_button():
    """Кнопка отмены (Reply)"""
    buttons = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_panel():
    """Админ-панель (Reply)"""
    buttons = [
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔗 Изменить ссылки")],
        [KeyboardButton(text="👨‍💻 Изменить операторов")],
        [KeyboardButton(text="◀️ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)