"""Кеш в памяти процесса — основной кеш при одном экземпляре приложения."""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float | None

    def is_alive(self, now: float) -> bool:
        return self.expires_at is None or self.expires_at > now


class MemoryCache:
    """Словарь со сроком жизни записей.

    Приложение однопроцессное и асинхронное: операции между ``await`` не
    прерываются, поэтому блокировка для согласованности не нужна.
    """

    def __init__(self) -> None:
        self._data: dict[str, _Entry] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if not entry.is_alive(time.monotonic()):
            del self._data[key]
            return None
        return entry.value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + ttl if ttl else None
        self._data[key] = _Entry(value=value, expires_at=expires_at)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._data.pop(key, None)

    async def delete_pattern(self, pattern: str) -> int:
        victims = [key for key in self._data if fnmatch.fnmatchcase(key, pattern)]
        for key in victims:
            del self._data[key]
        return len(victims)

    async def clear(self) -> None:
        self._data.clear()

    async def incr(self, key: str, ttl: int) -> int:
        """Увеличить счётчик. Срок жизни ставится при первом увеличении.

        Операция не содержит ожиданий, поэтому в однопроцессном
        приложении выполняется целиком и события не теряются.
        """
        entry = self._data.get(key)
        now = time.monotonic()
        if entry is None or not entry.is_alive(now):
            self._data[key] = _Entry(value=1, expires_at=now + ttl)
            return 1

        entry.value = int(entry.value) + 1
        return entry.value

    def purge_expired(self) -> int:
        """Убрать истёкшие записи. Вызывается фоновой задачей очистки."""
        now = time.monotonic()
        victims = [key for key, entry in self._data.items() if not entry.is_alive(now)]
        for key in victims:
            del self._data[key]
        return len(victims)

    def __len__(self) -> int:
        return len(self._data)
