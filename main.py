import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from config import BOT_TOKEN
from database import init_db
from utils import ensure_link_json
from start import router as start_router
from admin import router as admin_router
from send import router as send_router
from support import router as support_router

logging.basicConfig(level=logging.INFO)

# Middleware для блокировки всего, кроме личных сообщений
class PrivateOnlyMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            if event.chat.type != "private":
                return

        if isinstance(event, CallbackQuery):
            if event.message and event.message.chat.type != "private":
                return

        return await handler(event, data)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Подключаем middleware
dp.message.middleware(PrivateOnlyMiddleware())
dp.callback_query.middleware(PrivateOnlyMiddleware())

async def main():
    init_db()
    ensure_link_json()

    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(send_router)
    dp.include_router(support_router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())