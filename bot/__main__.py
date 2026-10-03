"""Точка входа: ``python -m bot``."""

from __future__ import annotations

import asyncio
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import User
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
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


async def wait_for_telegram(bot: Bot) -> User:
    """Дождаться связи с Telegram.

    На части серверов запросы к Telegram периодически обрываются по
    таймауту. Падать из-за этого нельзя: бот ждёт и пробует снова, пока
    связь не появится. Сдаётся он только на неверном токене, его
    повторы не исправят.
    """
    delay = 5
    attempt = 1
    while True:
        try:
            return await bot.get_me()
        except TelegramUnauthorizedError:
            raise SystemExit("Telegram отверг токен: проверьте BOT_TOKEN в .env") from None
        except (TelegramNetworkError, TelegramServerError, OSError, asyncio.TimeoutError) as exc:
            log.warning(
                "нет связи с Telegram (попытка %s): %s, повтор через %s сек.",
                attempt, exc, delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
            attempt += 1


async def set_commands(bot: Bot, settings: Settings) -> None:
    """В меню только /start. Служебные команды работают, но нигде не видны.

    Меню, выставленные прежними версиями бота для групп и для отдельных
    админов, удаляются: иначе Telegram продолжал бы их показывать.
    """
    await bot.set_my_commands(
        [BotCommand(command="start", description="Главное меню")],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
    for admin_id in settings.owner_ids | settings.admins:
        try:
            await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramBadRequest:
            pass  # админ ещё не писал боту


async def main() -> None:
    setup_logging()
    config = Config.from_env()

    db = Database(config.db_path)
    await db.connect()
    settings = Settings(db, config.owner_ids)
    await settings.load()

    session = AiohttpSession(proxy=config.proxy, timeout=config.request_timeout)
    if config.ipv4_only and not config.proxy:
        # На многих VPS IPv6 настроен, но не работает: соединение по нему
        # висит до таймаута, хотя по IPv4 Telegram доступен.
        session._connector_init["family"] = socket.AF_INET
    bot = Bot(config.bot_token, session=session)
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
        me = await wait_for_telegram(bot)
        log.info("бот @%s запущен, рабочая группа: %s", me.username, settings.group_id)
        try:
            await set_commands(bot, settings)
        except (TelegramNetworkError, TelegramServerError) as exc:
            log.warning("меню команд не обновлено: %s", exc)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
