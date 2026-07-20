from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardRemove

from database import add_user
from keyboards import main_menu, cancel_button
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

@router.message(F.text == "💬 Чат")
async def btn_chat(message: types.Message):
    link = get_link("chat")
    if link:
        await message.answer(f"🔗 Ссылка на чат:\n{link}")
    else:
        await message.answer("❌ Ссылка не настроена")

@router.message(F.text == "📢 Новости")
async def btn_news(message: types.Message):
    link = get_link("news")
    if link:
        await message.answer(f"🔗 Ссылка на новости:\n{link}")
    else:
        await message.answer("❌ Ссылка не настроена")

@router.message(F.text == "🛟 Резерв")
async def btn_reserve(message: types.Message):
    link = get_link("reserve")
    if link:
        await message.answer(f"🔗 Ссылка на резерв:\n{link}")
    else:
        await message.answer("❌ Ссылка не настроена")

@router.message(F.text == "🤖 Бот")
async def btn_bot(message: types.Message):
    link = get_link("bot")
    if link:
        await message.answer(f"🔗 Ссылка на бота:\n{link}")
    else:
        await message.answer("❌ Ссылка не настроена")

@router.message(F.text == "🌐 Сайт")
async def btn_website(message: types.Message):
    link = get_link("website")
    if link:
        await message.answer(f"🔗 Ссылка на сайт:\n{link}")
    else:
        await message.answer("❌ Ссылка не настроена")

@router.message(F.text == "👨‍💼 CEO")
async def btn_ceo(message: types.Message):
    link = get_link("ceo")
    if link:
        await message.answer(f"🔗 Контакт CEO:\n{link}")
    else:
        await message.answer("❌ Ссылка не настроена")

@router.message(F.text == "🎧 Оператор")
async def btn_operator(message: types.Message):
    link = get_link("operator")
    if link:
        await message.answer(f"🔗 Контакт оператора:\n{link}")
    else:
        await message.answer("❌ Ссылка не настроена")

@router.message(F.text == "✉️ Связаться с оператором")
async def btn_support(message: types.Message):
    """Переход в режим обращения к оператору"""
    await message.answer(
        "Опишите проблему одним сообщением.\n"
        "Поддерживаются только текстовые сообщения.\n\n"
        "Ответ придет прямо в этот чат.",
        reply_markup=cancel_button()
    )