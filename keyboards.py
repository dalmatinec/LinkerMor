from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from utils import get_link

def main_menu():
    """Главное меню с инлайн кнопками вместо текстовых ссылок"""
    buttons = [
        [KeyboardButton(text="💬 Чат"), KeyboardButton(text="📢 Новости")],
        [KeyboardButton(text="🛟 Резерв"), KeyboardButton(text="🤖 Бот")],
        [KeyboardButton(text="🌐 Сайт")],
        [KeyboardButton(text="👨‍💼 CEO"), KeyboardButton(text="🎧 Оператор")],
        [KeyboardButton(text="✉️ Связаться с оператором")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_inline_links():
    """Инлайн клавиатура со ссылками"""
    links = {
        "💬 Чат": get_link("chat"),
        "📢 Новости": get_link("news"),
        "🛟 Резерв": get_link("reserve"),
        "🤖 Бот": get_link("bot"),
        "🌐 Сайт": get_link("website"),
        "👨‍💼 CEO": get_link("ceo"),
        "🎧 Оператор": get_link("operator")
    }
    
    buttons = []
    for name, url in links.items():
        if url:
            buttons.append([InlineKeyboardButton(text=name, url=url)])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cancel_button():
    """Кнопка отмены"""
    buttons = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_panel():
    """Админ-панель"""
    buttons = [
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔗 Изменить ссылки")],
        [KeyboardButton(text="👨‍💻 Изменить операторов")],
        [KeyboardButton(text="◀️ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)