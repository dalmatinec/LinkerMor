import logging
from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardRemove

from config import ADMIN_IDS
from database import add_user
from utils import get_operators, format_user_message
from keyboards import main_menu

logger = logging.getLogger(__name__)
router = Router()

# Словарь для хранения сообщений пользователей
# {user_id: {"text": str, "message_id": int, "date": str}}
user_messages = {}

@router.message(F.text == "❌ Отмена")
async def cancel_support(message: types.Message):
    """Отмена обращения"""
    await message.answer(
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
    
    # Получаем операторов и админов
    operators = get_operators()
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
                text=formatted
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send to {recipient_id}: {e}")
    
    if sent_count > 0:
        await message.answer(
            "✅ Ваше обращение отправлено операторам.\n"
            "Ответ придет прямо в этот чат.",
            reply_markup=main_menu()
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
    
    # Проверяем, является ли отправитель оператором
    operators = get_operators()
    
    # Если это не оператор - игнорируем
    if user.id not in operators:
        return
    
    # Получаем оригинальное сообщение (реплай)
    replied_msg = message.reply_to_message
    
    # Проверяем, что это сообщение от бота (формат обращения)
    if not replied_msg or replied_msg.from_user.id != (await message.bot.get_me()).id:
        return
    
    # Пытаемся найти ID пользователя из текста сообщения
    # Ищем строку "🆔 ID\n123456789"
    text = replied_msg.text
    user_id = None
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "🆔 ID" in line and i + 1 < len(lines):
            try:
                user_id = int(lines[i + 1].strip())
                break
            except:
                pass
    
    if not user_id:
        await message.answer("❌ Не удалось определить пользователя")
        return
    
    # Формируем ответ пользователю
    answer_text = (
        f"💬 Ответ поддержки\n\n"
        f"👨‍💻 Ответил оператор\n\n"
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
    except Exception as e:
        logger.error(f"Failed to send reply to {user_id}: {e}")
        await message.answer(f"❌ Ошибка при отправке: {e}")

# Игнорируем все остальные сообщения
@router.message(F.content_type.in_({
    "photo", "video", "document", "animation", 
    "voice", "video_note", "sticker"
}))
async def handle_unsupported(message: types.Message):
    """Обработка неподдерживаемых типов сообщений"""
    await message.answer(
        "Поддерживаются только текстовые сообщения.",
        reply_markup=main_menu()
    )