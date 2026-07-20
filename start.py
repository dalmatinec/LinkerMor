from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardRemove

from database import add_user
from keyboards import main_menu, get_inline_links, cancel_button
from utils import get_link

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user = message.from_user
    
    # Регистрация пользователя
    add_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Добро пожаловать в нашего бота!\n"
        f"Используй кнопки меню для навигации.",
        reply_markup=main_menu()
    )

@router.message(F.text == "✉️ Связаться с оператором")
async def btn_support(message: types.Message):
    """Переход в режим обращения к оператору"""
    await message.answer(
        "Опишите проблему одним сообщением.\n"
        "Поддерживаются только текстовые сообщения.\n\n"
        "Ответ придет прямо в этот чат.",
        reply_markup=cancel_button()
    )

# Обработка всех кнопок со ссылками через инлайн
@router.message(F.text.in_(["💬 Чат", "📢 Новости", "🛟 Резерв", "🤖 Бот", "🌐 Сайт", "👨‍💼 CEO", "🎧 Оператор"]))
async def handle_link_buttons(message: types.Message):
    """Обработка кнопок с ссылками через инлайн клавиатуру"""
    await message.answer(
        "Выберите ссылку:",
        reply_markup=get_inline_links()
    )