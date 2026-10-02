"""Рассылка всем пользователям бота.

Идёт в фоне и медленнее общего лимита Telegram, чтобы живые ответы
поддержки не вставали в очередь за тысячами сообщений рассылки.
Одновременно может идти только одна рассылка.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import stored
from bot.db import Database
from bot.log import log
from bot.throttle import TokenBucket

PROGRESS_EVERY = 3.0  # секунд между обновлениями прогресса

STOP_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="⏹ Остановить", callback_data="a:bc:stop"),
]])


@dataclass
class Progress:
    total: int
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    started: float = field(default_factory=time.monotonic)

    @property
    def done(self) -> int:
        return self.sent + self.blocked + self.failed

    def text(self, finished: bool = False, stopped: bool = False) -> str:
        head = "⏹ Рассылка остановлена" if stopped else (
            "✅ Рассылка завершена" if finished else "📨 Идёт рассылка"
        )
        return (
            f"<b>{head}</b> · {self.done}/{self.total}\n\n"
            f"✅ Доставлено: <b>{self.sent}</b>\n"
            f"💤 Остановили бота: <b>{self.blocked}</b>\n"
            f"⚠️ Ошибки: <b>{self.failed}</b>\n"
            f"⏱ {int(time.monotonic() - self.started)}с"
        )


class Broadcaster:
    def __init__(self, rate: float) -> None:
        self.rate = rate
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def stop(self) -> None:
        self._stop.set()

    def start(
        self, bot: Bot, db: Database, message: dict[str, Any], ids: list[int],
        report_chat: int, report_msg: int,
    ) -> None:
        if self.running:
            raise RuntimeError("рассылка уже идёт")
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(bot, db, message, ids, report_chat, report_msg)
        )

    async def _run(
        self, bot: Bot, db: Database, message: dict[str, Any], ids: list[int],
        report_chat: int, report_msg: int,
    ) -> Progress:
        progress = Progress(total=len(ids))
        bucket = TokenBucket(self.rate)
        last_report = time.monotonic()
        for user_id in ids:
            if self._stop.is_set():
                break
            await bucket.acquire()
            try:
                await stored.send(bot, user_id, message)
                progress.sent += 1
            except TelegramForbiddenError:
                progress.blocked += 1
                await db.set_blocked_bot(user_id)
            except Exception as exc:  # noqa: BLE001 - один сбой не должен рвать рассылку
                progress.failed += 1
                log.warning("рассылка: %s не доставлено: %s", user_id, exc)
            if time.monotonic() - last_report >= PROGRESS_EVERY:
                last_report = time.monotonic()
                await self._report(bot, report_chat, report_msg, progress.text(), STOP_KB)

        stopped = self._stop.is_set()
        await self._report(
            bot, report_chat, report_msg, progress.text(finished=True, stopped=stopped), None
        )
        return progress

    @staticmethod
    async def _report(bot: Bot, chat_id: int, msg_id: int, text: str, kb) -> None:
        try:
            await bot.edit_message_text(
                text, chat_id=chat_id, message_id=msg_id, reply_markup=kb, parse_mode="HTML"
            )
        except TelegramBadRequest:
            pass  # текст не изменился или сообщение удалено
