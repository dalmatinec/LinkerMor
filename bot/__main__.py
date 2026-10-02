"""Точка входа: ``python -m bot``."""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

from bot.broadcast import Broadcaster
from bot.captcha import CaptchaStore
from bot.config import Config
from bot.db import Database
from bot.flood import FloodControl
from bot.handlers import build_router
from bot.log import log, setup_logging
from bot.settings import Settings
from bot.throttle import ThrottleMiddleware


async def set_commands(bot: Bot, settings: Settings) -> None:
    await bot.set_my_commands(
        [BotCommand(command="start", description="Начать")],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        [
            BotCommand(command="id", description="ID пользователя (ответом)"),
            BotCommand(command="ban", description="Забанить: ID или ответом"),
            BotCommand(command="unban", description="Разбанить по ID"),
            BotCommand(command="setgroup", description="Сделать группу рабочей"),
        ],
        scope=BotCommandScopeAllGroupChats(),
    )
    admin_commands = [
        BotCommand(command="admin", description="Админка"),
        BotCommand(command="ban", description="Забанить по ID"),
        BotCommand(command="unban", description="Разбанить по ID"),
        BotCommand(command="cancel", description="Отменить ввод"),
        BotCommand(command="start", description="Начать как пользователь"),
    ]
    for admin_id in settings.owner_ids | settings.admins:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramBadRequest:
            pass  # админ ещё не писал боту


async def main() -> None:
    setup_logging()
    config = Config.from_env()

    db = Database(config.db_path)
    await db.connect()
    settings = Settings(db, config.owner_ids)
    await settings.load()

    bot = Bot(config.bot_token)
    bot.session.middleware(ThrottleMiddleware(
        global_rate=config.global_rate,
        private_burst=config.private_burst,
        private_period=config.private_period,
        group_per_minute=config.group_per_minute,
    ))

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router())
    dp["db"] = db
    dp["settings"] = settings
    dp["config"] = config
    dp["flood"] = FloodControl()
    dp["captchas"] = CaptchaStore()
    dp["broadcaster"] = Broadcaster(config.broadcast_rate)

    try:
        me = await bot.get_me()
        log.info("бот @%s запущен, рабочая группа: %s", me.username, settings.group_id)
        await set_commands(bot, settings)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
