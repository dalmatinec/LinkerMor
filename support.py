# support.py

import logging
import re
from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardRemove

from config import ADMIN_IDS
from database import add_user
from utils import get_operators, format_user_message
from keyboards import main_menu

logger = logging.getLogger(__name__)
router = Router()

# Словарь для хранения сообщений пользователей
user_messages = {}

@router.callback_query(F.data == "cancel_support")
async def callback_cancel(callback: types.CallbackQuery):
    """Отмена обращения через инлайн кнопку"""
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer(
        "❌ Обращение отменено",
        reply_markup=main_menu()
    )

@router.message(F.text)
async def handle_support_message(message: types.Message):
    """Обработка текстовых сообщений в режиме поддержки"""
    user = message.from_user
    
    # Проверяем, что это не команда
    if message.text.startswith("/"):
        return
    
    # Проверяем, не является ли отправитель оператором или админом
    operators = get_operators()
    if user.id in operators or user.id in ADMIN_IDS:
        return
    
    # Получаем операторов и админов
    recipients = list(set(ADMIN_IDS + operators))
    
    if not recipients:
        await message.answer(
            "❌ В данный момент нет доступных операторов.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    # Сохраняем сообщение пользователя
    user_messages[user.id] = {
        "text": message.text,
        "message_id": message.message_id,
        "date": message.date
    }
    
    # Форматируем сообщение для отправки
    formatted = format_user_message(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        text=message.text
    )
    
    # Отправляем всем получателям
    sent_count = 0
    for recipient_id in recipients:
        try:
            await message.bot.send_message(
                chat_id=recipient_id,
                text=formatted,
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send to {recipient_id}: {e}")
    
    # Удаляем сообщение пользователя
    await message.delete()
    
    if sent_count > 0:
        await message.answer(
            "✅ Ваше обращение отправлено операторам.\n"
            "Ответ придет в ближайшее время."
        )
    else:
        await message.answer(
            "❌ Не удалось отправить обращение.\n"
            "Попробуйте позже.",
            reply_markup=main_menu()
        )

@router.message(F.reply_to_message)
async def handle_operator_reply(message: types.Message):
    """Обработка ответа оператора реплаем"""
    user = message.from_user
    
    # Логи для отладки
    logger.info(f"Reply from user: {user.id}")
    
    # Проверяем, является ли отправитель оператором
    operators = get_operators()
    logger.info(f"Operators list: {operators}")
    logger.info(f"Is operator? {user.id in operators}")
    
    # Если это не оператор - игнорируем
    if user.id not in operators:
        logger.info("Not operator, ignoring")
        return
    
    # Получаем оригинальное сообщение (реплай)
    replied_msg = message.reply_to_message
    
    # Проверяем, что это сообщение от бота
    bot_id = (await message.bot.get_me()).id
    if not replied_msg or replied_msg.from_user.id != bot_id:
        logger.info("Not a reply to bot message")
        return
    
    # Пытаемся найти ID пользователя из текста сообщения
    text = replied_msg.text
    user_id = None
    
    # Ищем ID в формате "🆔 ID\n123456789"
    match = re.search(r'🆔 ID\n(\d+)', text)
    if match:
        user_id = int(match.group(1))
        logger.info(f"Found user_id: {user_id}")
    
    if not user_id:
        await message.answer("❌ Не удалось определить пользователя")
        return
    
    # Получаем имя оператора
    operator_name = user.first_name or user.username or str(user.id)
    
    # Если ответ - текстовое сообщение
    if message.text:
        answer_text = (
            f"💬 Ответ поддержки\n\n"
            f"👨‍💻 Ответил: {operator_name}\n\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"{message.text}\n\n"
            f"━━━━━━━━━━━━━━"
        )
        try:
            await message.bot.send_message(
                chat_id=user_id,
                text=answer_text
            )
            await message.answer("✅ Ответ отправлен пользователю")
            logger.info(f"Reply sent to {user_id}")
        except Exception as e:
            logger.error(f"Failed to send reply to {user_id}: {e}")
            await message.answer(f"❌ Ошибка при отправке: {e}")
    
    # Если ответ - фото
    elif message.photo:
        try:
            caption = (
                f"💬 Ответ поддержки\n\n"
                f"👨‍💻 Ответил: {operator_name}\n\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"{message.caption or ''}\n\n"
                f"━━━━━━━━━━━━━━"
            ) if message.caption else (
                f"💬 Ответ поддержки\n\n"
                f"👨‍💻 Ответил: {operator_name}\n\n"
                f"━━━━━━━━━━━━━━"
            )
            await message.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=caption
            )
            await message.answer("✅ Ответ отправлен пользователю")
            logger.info(f"Photo reply sent to {user_id}")
        except Exception as e:
            logger.error(f"Failed to send photo reply to {user_id}: {e}")
            await message.answer(f"❌ Ошибка при отправке: {e}")
    
    # Если ответ - видео
    elif message.video:
        try:
            caption = (
                f"💬 Ответ поддержки\n\n"
                f"👨‍💻 Ответил: {operator_name}\n\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"{message.caption or ''}\n\n"
                f"━━━━━━━━━━━━━━"
            ) if message.caption else (
                f"💬 Ответ поддержки\n\n"
                f"👨‍💻 Ответил: {operator_name}\n\n"
                f"━━━━━━━━━━━━━━"
            )
            await message.bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=caption
            )
            await message.answer("✅ Ответ отправлен пользователю")
            logger.info(f"Video reply sent to {user_id}")
        except Exception as e:
            logger.error(f"Failed to send video reply to {user_id}: {e}")
            await message.answer(f"❌ Ошибка при отправке: {e}")
    
    # Если ответ - документ
    elif message.document:
        try:
            caption = (
                f"💬 Ответ поддержки\n\n"
                f"👨‍💻 Ответил: {operator_name}\n\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"{message.caption or ''}\n\n"
                f"━━━━━━━━━━━━━━"
            ) if message.caption else (
                f"💬 Ответ поддержки\n\n"
                f"👨‍💻 Ответил: {operator_name}\n\n"
                f"━━━━━━━━━━━━━━"
            )
            await message.bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=caption
            )
            await message.answer("✅ Ответ отправлен пользователю")
            logger.info(f"Document reply sent to {user_id}")
        except Exception as e:
            logger.error(f"Failed to send document reply to {user_id}: {e}")
            await message.answer(f"❌ Ошибка при отправке: {e}")
    
    # Если ответ - другие типы
    else:
        await message.answer("❌ Этот тип сообщения не поддерживается для отправки пользователю")

# Игнорируем все неподдерживаемые сообщения от пользователей
@router.message(F.content_type.in_({
    "photo", "video", "document", "animation", 
    "voice", "video_note", "sticker"
}))
async def handle_unsupported(message: types.Message):
    """Обработка неподдерживаемых типов сообщений от пользователей"""
    user = message.from_user
    
    # Проверяем, не является ли отправитель оператором или админом
    operators = get_operators()
    if user.id in operators or user.id in ADMIN_IDS:
        return
    
    await message.answer(
        "Поддерживаются только текстовые сообщения.",
        reply_markup=main_menu()
    )