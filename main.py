import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database import init_db
from utils import ensure_link_json
from start import router as start_router
from admin import router as admin_router
from send import router as send_router
from support import router as support_router

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

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