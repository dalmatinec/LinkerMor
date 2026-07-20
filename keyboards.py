from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
    """Админ-панель (инлайн)"""
    buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔗 Изменить ссылки", callback_data="admin_edit_links")],
        [InlineKeyboardButton(text="👨‍💻 Изменить операторов", callback_data="admin_edit_operators")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="admin_back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)