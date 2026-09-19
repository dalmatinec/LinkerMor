"""Ограничение частоты отправки (ТЗ §24).

Telegram применяет два независимых лимита: около 30 сообщений в секунду в
сумме и примерно одно сообщение в три секунды в один и тот же групповой
чат. Превышение возвращает ошибку с требованием подождать, а при упорстве
приводит к временной блокировке бота.

Всплески возникают буднично: несколько человек заходят в чат одновременно,
и приветствие с капчей мгновенно упирается в лимит. Поэтому отправка идёт
через ограничитель, а не напрямую.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable

#: Минимальный промежуток между сообщениями в один групповой чат.
DEFAULT_CHAT_INTERVAL = 3.0

#: Потолок отправки в сумме по всем чатам, сообщений в секунду.
DEFAULT_GLOBAL_RATE = 25


class RateLimiter:
    """Пропускает отправку не чаще разрешённого.

    Часы и ожидание передаются параметрами, чтобы тесты проверяли поведение
    без реальных задержек.
    """

    def __init__(
        self,
        chat_interval: float = DEFAULT_CHAT_INTERVAL,
        global_rate: int = DEFAULT_GLOBAL_RATE,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._chat_interval = chat_interval
        self._global_rate = global_rate
        self._clock = clock or asyncio.get_event_loop().time
        self._sleep = sleep or asyncio.sleep

        self._last_sent: dict[int, float] = {}
        self._recent: deque[float] = deque()
        self._locks: dict[int, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def _lock_for(self, chat_id: int) -> asyncio.Lock:
        lock = self._locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[chat_id] = lock
        return lock

    async def acquire(self, chat_id: int) -> float:
        """Дождаться разрешения на отправку в чат.

        Returns:
            Сколько секунд пришлось ждать. Используется в тестах и метриках.
        """
        waited = 0.0

        # Лимит чата: сообщения в один чат разносятся по времени.
        async with self._lock_for(chat_id):
            last = self._last_sent.get(chat_id)
            now = self._clock()
            if last is not None:
                delay = self._chat_interval - (now - last)
                if delay > 0:
                    await self._sleep(delay)
                    waited += delay
            self._last_sent[chat_id] = self._clock()

        # Общий лимит: считаем отправки за последнюю секунду.
        async with self._global_lock:
            now = self._clock()
            while self._recent and now - self._recent[0] >= 1.0:
                self._recent.popleft()
            if len(self._recent) >= self._global_rate:
                delay = 1.0 - (now - self._recent[0])
                if delay > 0:
                    await self._sleep(delay)
                    waited += delay
                    now = self._clock()
                    while self._recent and now - self._recent[0] >= 1.0:
                        self._recent.popleft()
            self._recent.append(self._clock())

        return waited

    def forget(self, chat_id: int) -> None:
        """Забыть состояние чата: бот покинул его или чат переехал."""
        self._last_sent.pop(chat_id, None)
        self._locks.pop(chat_id, None)
