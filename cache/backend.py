"""Контракт кеша.

При одном экземпляре приложения хватает кеша в памяти процесса, поэтому
инвалидация мгновенная и не требует Redis. Контракт вынесен в протокол,
чтобы переход на несколько экземпляров был заменой реализации, а не
переписыванием сервисов.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """Минимальный набор операций, который используют сервисы."""

    async def get(self, key: str) -> Any | None:
        """Значение или ``None``, если ключа нет либо истёк срок жизни."""
        ...

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Записать значение с необязательным временем жизни в секундах."""
        ...

    async def delete(self, *keys: str) -> None:
        """Удалить ключи. Отсутствующие игнорируются."""
        ...

    async def delete_pattern(self, pattern: str) -> int:
        """Удалить ключи по шаблону с ``*``. Возвращает число удалённых."""
        ...

    async def clear(self) -> None:
        """Полная очистка. Используется в тестах и при остановке."""
        ...
