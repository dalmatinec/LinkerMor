"""Единая точка доступа к настройкам (ТЗ §23).

Ни один хендлер не читает настройки напрямую из базы или кеша: все
обращения проходят через этот сервис. Благодаря этому путь значения всегда
один и тот же:

``база → кеш → рантайм → изменение → сброс кеша → новое значение → перезапуск``

Значения по умолчанию берутся из реестра определений, поэтому настройка,
которую чат никогда не менял, всё равно имеет корректное значение, а
изменённая — переживает перезапуск, потому что лежит в базе.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from core.logging import get_logger
from settings.defs import SettingsRegistry
from settings.repo import SettingsRepository

log = get_logger(__name__)

#: Срок жизни кеша настроек. При одном экземпляре приложения инвалидация
#: происходит мгновенно, и TTL служит лишь страховкой.
SETTINGS_CACHE_TTL = 300


class SettingsService:
    """Чтение и изменение настроек чата."""

    def __init__(
        self,
        session: AsyncSession,
        cache: CacheBackend,
        registry: SettingsRegistry,
    ) -> None:
        self._session = session
        self._cache = cache
        self._registry = registry
        self._repo = SettingsRepository(session)

    # ─── Чтение ──────────────────────────────────────────────────────────────

    async def all(self, chat_id: int) -> dict[str, Any]:
        """Все настройки чата: значения по умолчанию поверх переопределений."""
        key = chat_key(ChatEntity.SETTINGS, chat_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        values = self._registry.defaults()
        values.update(await self._repo.load_overrides(chat_id))
        await self._cache.set(key, values, ttl=SETTINGS_CACHE_TTL)
        return values

    async def get(self, chat_id: int, key: str) -> Any:
        """Значение одной настройки.

        Raises:
            SettingValidationError: настройки с таким ключом не существует.
        """
        definition = self._registry.get(key)
        values = await self.all(chat_id)
        return values.get(key, definition.default)

    async def get_many(self, chat_id: int, prefix: str) -> dict[str, Any]:
        """Настройки одного модуля: ``get_many(chat_id, "welcome.")``."""
        values = await self.all(chat_id)
        return {k: v for k, v in values.items() if k.startswith(prefix)}

    async def is_module_enabled(self, chat_id: int, module: str) -> bool:
        """Включён ли модуль в этом чате.

        Модули, которые нельзя отключать, в реестре настроек отсутствуют и
        считаются включёнными всегда.
        """
        from settings.defs import module_toggle_key

        key = module_toggle_key(module)
        if not self._registry.has(key):
            return True
        return bool(await self.get(chat_id, key))

    # ─── Изменение ───────────────────────────────────────────────────────────

    async def set(self, chat_id: int, key: str, value: Any, actor_id: int | None = None) -> Any:
        """Изменить настройку чата.

        Значение проверяется определением, записывается в базу, попадает в
        журнал изменений, после чего кеш этого — и только этого — чата
        сбрасывается.

        Returns:
            Значение после приведения к типу настройки.
        """
        definition = self._registry.get(key)
        coerced = definition.coerce(value)

        previous = await self.get(chat_id, key)
        await self._repo.upsert(chat_id, key, coerced, actor_id)
        await self._repo.record_change(chat_id, key, previous, coerced, actor_id)
        await self._invalidate(chat_id)

        log.info(
            "настройка изменена",
            extra={"chat_id": chat_id, "setting": key, "old": previous, "new": coerced,
                   "actor": actor_id},
        )
        return coerced

    async def reset(self, chat_id: int, key: str, actor_id: int | None = None) -> Any:
        """Вернуть настройку к значению по умолчанию."""
        definition = self._registry.get(key)
        previous = await self.get(chat_id, key)

        await self._repo.delete(chat_id, key)
        await self._repo.record_change(chat_id, key, previous, definition.default, actor_id)
        await self._invalidate(chat_id)

        log.info(
            "настройка сброшена",
            extra={"chat_id": chat_id, "setting": key, "actor": actor_id},
        )
        return definition.default

    async def history(self, chat_id: int, limit: int = 20) -> list:
        """Последние изменения настроек чата — для панели и аудита."""
        return await self._repo.history(chat_id, limit)

    async def _invalidate(self, chat_id: int) -> None:
        """Сбросить кеш настроек одного чата.

        Ключ содержит ``chat_id``, поэтому настройки соседних чатов
        остаются в кеше нетронутыми.
        """
        await self._cache.delete(chat_key(ChatEntity.SETTINGS, chat_id))
