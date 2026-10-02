"""Антифлуд для исходящих сообщений.

Telegram ограничивает ботов: около 30 сообщений в секунду всего, около
одного в секунду в один личный чат и 20 в минуту в одну группу. При
превышении приходит ``429 Too Many Requests``, а при систематическом
временная блокировка бота.

Ограничение встроено в HTTP-сессию бота как middleware, поэтому через
него проходит любая отправка: из хендлеров, рассылки, уведомлений,
и забыть его в новом месте нельзя. Сообщения в один чат уходят строго
по очереди, порядок не нарушается.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramRetryAfter

from bot.log import log

MAX_RETRIES = 3


class TokenBucket:
    """Не больше ``rate`` событий в секунду, всплеск до ``capacity``."""

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self.rate = rate
        self.capacity = capacity if capacity is not None else max(1.0, rate)
        self._tokens = self.capacity
        self._stamp = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._stamp) * self.rate)
                self._stamp = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self.rate)


class SlidingWindow:
    """Не больше ``limit`` событий за ``period`` секунд."""

    def __init__(self, limit: int, period: float) -> None:
        self.limit = limit
        self.period = period
        self.events: deque[float] = deque()

    def delay(self, now: float) -> float:
        while self.events and now - self.events[0] >= self.period:
            self.events.popleft()
        if len(self.events) < self.limit:
            return 0.0
        return self.period - (now - self.events[0])

    def record(self, now: float) -> None:
        self.events.append(now)


@dataclass
class _ChatState:
    window: SlidingWindow
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    used: float = 0.0


def is_sending(api_method: str) -> bool:
    return api_method.startswith(("send", "copy", "forward")) and api_method != "sendChatAction"


class ThrottleMiddleware(BaseRequestMiddleware):
    def __init__(
        self,
        global_rate: float,
        private_burst: int,
        private_period: float,
        group_per_minute: int,
    ) -> None:
        self.bucket = TokenBucket(global_rate)
        self.private = (private_burst, private_period)
        self.group = (group_per_minute, 60.0)
        self._chats: dict[int | str, _ChatState] = {}

    def _state(self, chat_id: int | str) -> _ChatState:
        state = self._chats.get(chat_id)
        if state is None:
            if len(self._chats) > 5000:
                self._prune()
            is_private = isinstance(chat_id, int) and chat_id > 0
            limit, period = self.private if is_private else self.group
            state = self._chats[chat_id] = _ChatState(SlidingWindow(limit, period))
        return state

    def _prune(self) -> None:
        """Забыть чаты, куда давно ничего не отправлялось."""
        now = time.monotonic()
        for key, st in list(self._chats.items()):
            if not st.lock.locked() and now - st.used > 120:
                del self._chats[key]

    async def __call__(self, make_request, bot, method):
        chat_id = getattr(method, "chat_id", None)
        if chat_id is None or not is_sending(method.__api_method__):
            return await self._send(make_request, bot, method)

        state = self._state(chat_id)
        async with state.lock:
            wait = state.window.delay(time.monotonic())
            if wait > 0:
                await asyncio.sleep(wait)
            await self.bucket.acquire()
            state.window.record(time.monotonic())
            state.used = time.monotonic()
            return await self._send(make_request, bot, method)

    async def _send(self, make_request, bot, method):
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as exc:
                if attempt == MAX_RETRIES:
                    raise
                log.warning(
                    "Telegram просит подождать %s с (%s), попытка %s",
                    exc.retry_after, method.__api_method__, attempt + 1,
                )
                await asyncio.sleep(exc.retry_after + 0.5)
        raise AssertionError("unreachable")
