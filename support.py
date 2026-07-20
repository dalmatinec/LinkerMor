# support.py

import logging
from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardRemove

from config import ADMIN_IDS
from database import add_user
from utils import get_operators, format_user_message
from keyboards import main_menu

logger = logging.getLogger(__name__)
router = Router()

# Словарь для хранения соответствия: message_id сообщения оператору -> user_id
support_messages = {}

@router.message(F.text, ~F.reply_to_message)
async def handle_support_message(message: types.Message):
    """Обработка текстовых сообщений в режиме поддержки"""
    
    # Игнорируем сообщения из групп, супергрупп и каналов
    if message.chat.type in ["group", "supergroup", "channel"]:
        return
    
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

    # Форматируем сообщение для отправки
    formatted = format_user_message(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        text=message.text
    )

    # Отправляем всем получателям и сохраняем соответствие message_id -> user_id
    sent_count = 0
    for recipient_id in recipients:
        try:
            sent_msg = await message.bot.send_message(
                chat_id=recipient_id,
                text=formatted,
                parse_mode="HTML"
            )
            # Сохраняем соответствие: message_id сообщения оператору -> user_id пользователя
            support_messages[sent_msg.message_id] = user.id
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send to {recipient_id}: {e}")

    if sent_count > 0:
        await message.answer(
            "✅ Ваше обращение отправлено операторам.\n"
            "Ответ придет в ближайшее время.\n\n"
            "Для выхода в главное меню нажмите /start"
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
    logger.info(f"Reply handler started. From user: {message.from_user.id}")

    user = message.from_user

    # Проверяем, является ли отправитель оператором
    operators = get_operators()
    logger.info(f"Operators: {operators}")
    logger.info(f"Is operator: {message.from_user.id in operators}")

    # Если это не оператор - игнорируем
    if user.id not in operators:
        return

    # Получаем оригинальное сообщение (реплай)
    replied_msg = message.reply_to_message
    logger.info(f"reply_to_message exists: {replied_msg is not None}")
    if replied_msg:
        logger.info(f"reply message_id: {replied_msg.message_id}")
        logger.info(f"reply from: {replied_msg.from_user.id}")

    # Проверяем, что это сообщение от бота
    bot_id = (await message.bot.get_me()).id
    if not replied_msg or replied_msg.from_user.id != bot_id:
        return

    logger.info(f"support_messages: {support_messages}")
    logger.info(f"Looking for message_id: {replied_msg.message_id}")

    # Получаем ID пользователя из словаря по message_id
    user_id = support_messages.get(replied_msg.message_id)
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
            logger.info(f"Sending reply to user {user_id}")
            await message.bot.send_message(
                chat_id=user_id,
                text=answer_text
            )
            await message.answer("✅ Ответ отправлен пользователю")
            del support_messages[replied_msg.message_id]
        except Exception as e:
            logger.exception(e)
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
            logger.info(f"Sending photo reply to user {user_id}")
            await message.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=caption
            )
            await message.answer("✅ Ответ отправлен пользователю")
            del support_messages[replied_msg.message_id]
        except Exception as e:
            logger.exception(e)
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
            logger.info(f"Sending video reply to user {user_id}")
            await message.bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=caption
            )
            await message.answer("✅ Ответ отправлен пользователю")
            del support_messages[replied_msg.message_id]
        except Exception as e:
            logger.exception(e)
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
            logger.info(f"Sending document reply to user {user_id}")
            await message.bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=caption
            )
            await message.answer("✅ Ответ отправлен пользователю")
            del support_messages[replied_msg.message_id]
        except Exception as e:
            logger.exception(e)
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