"""Точка входа LinkerMor.

Запуск: ``python main.py``. Конфигурация берётся из окружения или ``.env``.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from core.bootstrap import ALLOWED_UPDATES, AppContext, build_app
from core.config import get_settings
from core.logging import get_logger, setup_logging

log = get_logger(__name__)


async def run(app: AppContext) -> None:
    """Принимать апдейты до сигнала остановки."""
    app.scheduler.start()
    me = await app.bot.get_me()
    log.info("бот запущен", extra={"bot": f"@{me.username}", "bot_id": me.id})

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
