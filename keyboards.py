from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from utils import get_link

def main_menu():
    """Главное меню со ссылками"""
    buttons = [
        [KeyboardButton(text="💬 Чат"), KeyboardButton(text="📢 Новости")],
        [KeyboardButton(text="🛟 Резерв"), KeyboardButton(text="🤖 Бот")],
        [KeyboardButton(text="🌐 Сайт")],
        [KeyboardButton(text="👨‍💼 CEO"), KeyboardButton(text="🎧 Оператор")],
        [KeyboardButton(text="✉️ Связаться с оператором")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

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

def admin_stats():
    """Статистика в админке"""
    # Используется в admin.py для вывода статистики
    pass