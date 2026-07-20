import asyncio
import logging
from typing import Dict, Any

from aiogram import Bot, Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter

from config import ADMIN_IDS
from database import get_all_users, mark_user_blocked, get_user_count, get_active_user_count, get_blocked_user_count

logger = logging.getLogger(__name__)
router = Router()

# Проверка на админа
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("send"))
async def cmd_send(message: Message):
    """Команда /send - рассылка текста/фото/видео"""
    if not is_admin(message.from_user.id):
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение, которое хотите разослать")
        return
    
    await message.answer("🔄 Начинаю рассылку...")
    
    result = await send_broadcast(message.bot, message.reply_to_message)
    
    await message.answer(
        f"📨 Рассылка завершена\n\n"
        f"👥 Всего пользователей: {result['total']}\n"
        f"✅ Отправлено: {result['sent']}\n"
        f"🚫 Заблокировали бота: {result['blocked']}\n"
        f"❌ Ошибок: {result['errors']}\n"
        f"⏱ Время выполнения: {result['time']} сек."
    )

@router.message(Command("forward"))
async def cmd_forward(message: Message):
    """Команда /forward - пересылка сообщения"""
    if not is_admin(message.from_user.id):
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение, которое хотите переслать")
        return
    
    await message.answer("🔄 Начинаю пересылку...")
    
    result = await forward_broadcast(message.bot, message.reply_to_message)
    
    await message.answer(
        f"📨 Рассылка завершена\n\n"
        f"👥 Всего пользователей: {result['total']}\n"
        f"✅ Отправлено: {result['sent']}\n"
        f"🚫 Заблокировали бота: {result['blocked']}\n"
        f"❌ Ошибок: {result['errors']}\n"
        f"⏱ Время выполнения: {result['time']} сек."
    )

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Команда /stats - статистика"""
    if not is_admin(message.from_user.id):
        return
    
    total = get_user_count()
    active = get_active_user_count()
    blocked = get_blocked_user_count()
    
    await message.answer(
        f"📊 Статистика\n\n"
        f"👥 Всего пользователей: {total}\n"
        f"✅ Активных: {active}\n"
        f"🚫 Заблокировали бота: {blocked}"
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help - помощь для админов"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "🤖 Команды администратора:\n\n"
        "/stats - Статистика пользователей\n"
        "/send - Рассылка (ответьте на сообщение)\n"
        "/forward - Пересылка (ответьте на сообщение)\n"
        "/help - Эта справка"
    )

async def send_broadcast(bot: Bot, admin_message: Message) -> Dict[str, Any]:
    """Рассылка текста/фото/видео"""
    import time
    start_time = time.time()
    
    users = get_all_users()
    if not users:
        return {"total": 0, "sent": 0, "failed": 0, "blocked": 0, "errors": 0, "time": 0}
    
    total = len(users)
    sent = 0
    blocked = 0
    errors = 0
    
    for user_id, is_blocked in users:
        if is_blocked:
            continue
            
        try:
            await admin_message.copy_to(
                chat_id=user_id,
                reply_markup=None
            )
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            logger.warning(f"Retry after {e.retry_after}s for user {user_id}")
            await asyncio.sleep(e.retry_after)
            try:
                await admin_message.copy_to(
                    chat_id=user_id,
                    reply_markup=None
                )
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e2:
                error = str(e2).lower()
                if "blocked" in error or "bot was blocked" in error:
                    mark_user_blocked(user_id)
                    blocked += 1
                else:
                    errors += 1
                logger.error(f"Send broadcast retry failed for {user_id}: {e2}")
        except Exception as e:
            error = str(e).lower()
            if "blocked" in error or "bot was blocked" in error:
                mark_user_blocked(user_id)
                blocked += 1
            else:
                errors += 1
            logger.error(f"Send broadcast failed for {user_id}: {e}")
    
    elapsed_time = round(time.time() - start_time, 2)
    
    return {
        "total": total,
        "sent": sent,
        "failed": total - sent,
        "blocked": blocked,
        "errors": errors,
        "time": elapsed_time
    }

async def forward_broadcast(bot: Bot, admin_message: Message) -> Dict[str, Any]:
    """Пересылка сообщения"""
    import time
    start_time = time.time()
    
    users = get_all_users()
    if not users:
        return {"total": 0, "sent": 0, "failed": 0, "blocked": 0, "errors": 0, "time": 0}
    
    total = len(users)
    sent = 0
    blocked = 0
    errors = 0
    
    for user_id, is_blocked in users:
        if is_blocked:
            continue
            
        try:
            await admin_message.forward(
                chat_id=user_id
            )
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            logger.warning(f"Retry after {e.retry_after}s for user {user_id}")
            await asyncio.sleep(e.retry_after)
            try:
                await admin_message.forward(
                    chat_id=user_id
                )
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e2:
                error = str(e2).lower()
                if "blocked" in error or "bot was blocked" in error:
                    mark_user_blocked(user_id)
                    blocked += 1
                else:
                    errors += 1
                logger.error(f"Forward broadcast retry failed for {user_id}: {e2}")
        except Exception as e:
            error = str(e).lower()
            if "blocked" in error or "bot was blocked" in error:
                mark_user_blocked(user_id)
                blocked += 1
            else:
                errors += 1
            logger.error(f"Forward broadcast failed for {user_id}: {e}")
    
    elapsed_time = round(time.time() - start_time, 2)
    
    return {
        "total": total,
        "sent": sent,
        "failed": total - sent,
        "blocked": blocked,
        "errors": errors,
        "time": elapsed_time
    }