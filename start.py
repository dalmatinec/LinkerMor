# start.py

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardRemove

from database import add_user
from keyboards import main_menu, cancel_inline
from utils import get_link

router = Router()

# Словарь с названиями ссылок
LINK_NAMES = {
    "chat": "💬 Чат",
    "news": "📢 Новости",
    "reserve": "🛟 Резерв",
    "bot": "🤖 Бот",
    "website": "🌐 Сайт",
    "ceo": "👨‍💼 CEO",
    "operator": "🎧 Оператор"
}

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

@router.callback_query(F.data.startswith("link_"))
async def callback_link(callback: types.CallbackQuery):
    """Обработчик кнопок со ссылками"""
    await callback.answer()
    
    link_key = callback.data.replace("link_", "")
    link_name = LINK_NAMES.get(link_key, link_key)
    url = get_link(link_key)
    
    if url:
        await callback.message.answer(
            f"{link_name}\n\n"
            f"🔗 {url}"
        )
    else:
        await callback.message.answer(
            f"❌ Ссылка не настроена"
        )

@router.callback_query(F.data == "support")
async def callback_support(callback: types.CallbackQuery):
    """Обработчик кнопки 'Связаться с оператором'"""
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer(
        "Опишите проблему одним сообщением.\n"
        "Поддерживаются только текстовые сообщения.\n\n"
        "Ответ придет прямо в этот чат.",
        reply_markup=cancel_inline()
    )

@router.callback_query(F.data == "cancel_support")
async def callback_cancel(callback: types.CallbackQuery):
    """Отмена обращения"""
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer(
        "❌ Обращение отменено",
        reply_markup=main_menu()
    )