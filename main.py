"""Точка входа LinkerMor.

Запуск: ``python main.py``. Конфигурация берётся из окружения или ``.env``.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiohttp import ClientError

from core.bootstrap import ALLOWED_UPDATES, AppContext, build_app
from core.config import get_settings
from core.logging import get_logger, setup_logging

log = get_logger(__name__)


async def check_connection(app: AppContext):
    """Убедиться, что бот может говорить с Telegram.

    Проверка отделена от запуска, чтобы две самые частые ошибки первого
    запуска — опечатка в токене и закрытая сеть — выглядели как понятное
    сообщение, а не как traceback на сорок строк.
    """
    try:
        return await app.bot.get_me()
    except TelegramUnauthorizedError:
        log.error(
            "Telegram отверг токен. Проверьте BOT_TOKEN в .env — "
            "его выдаёт @BotFather, и он мог быть отозван"
        )
    except (TelegramNetworkError, ClientError, OSError) as exc:
        log.error(
            "нет связи с Telegram. Проверьте сеть сервера и доступность "
            "api.telegram.org",
            extra={"reason": str(exc)[:200]},
        )
    return None


async def run(app: AppContext) -> None:
    """Принимать апдейты до сигнала остановки."""
    me = await check_connection(app)
    if me is None:
        return

    app.scheduler.start()
    log.info("бот запущен", extra={"bot": f"@{me.username}", "bot_id": me.id})

    # Владелец должен видеть каждый запуск: неожиданный запуск означает,
    # что до него был незамеченный сбой.
    await app.notifier.notify(
        f"Бот запущен: @{me.username}\nМодулей подключено: {len(app.registry.specs)}",
        force=True,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    polling = asyncio.create_task(
        app.dispatcher.start_polling(
            app.bot,
            allowed_updates=ALLOWED_UPDATES,
            handle_signals=False,
        )
    )
    await asyncio.wait([polling, asyncio.create_task(stop.wait())], return_when=asyncio.FIRST_COMPLETED)

    log.info("получен сигнал остановки")
    await app.notifier.notify("Бот остановлен.", force=True)
    await app.dispatcher.stop_polling()
    with contextlib.suppress(asyncio.CancelledError):
        await polling


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)

    app = build_app(settings)
    try:
        await run(app)
    finally:
        await app.shutdown()


if __name__ == "__main__":
    with contextlib.suppress(ImportError):
        import uvloop

        uvloop.install()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
