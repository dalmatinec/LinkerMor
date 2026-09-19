"""Защита от налётов (массового входа).

Налёт отличается от обычного притока людей скоростью: два десятка входов
за полминуты почти всегда означают атаку. Бот замечает всплеск и на время
ужесточает приём новых участников, а затем сам возвращает обычный режим.

Состояние тревоги хранится в кеше со сроком жизни. Это сознательный
выбор: тревога обязана заканчиваться сама, даже если бот перезапустится
посреди налёта и некому будет её снять.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from core.logging import get_logger
from mod_antiraid.models import RaidEvent
from settings.service import SettingsService

log = get_logger(__name__)


class RaidAction(StrEnum):
    """Что делать с теми, кто входит во время тревоги."""

    CAPTCHA = "captcha"  # проверка обязательна, даже если обычно выключена
    MUTE = "mute"  # вход разрешён, писать сразу нельзя
    KICK = "kick"  # удалять с правом вернуться позже
    BAN = "ban"  # закрыть вход совсем


@dataclass(frozen=True, slots=True)
class RaidStatus:
    """Положение дел в чате."""

    active: bool
    joins: int = 0
    #: Тревога включилась именно сейчас — об этом нужно сообщить.
    just_started: bool = False
    action: str = RaidAction.CAPTCHA


class RaidService:
    """Замечает всплески входов и держит режим тревоги."""

    def __init__(
        self,
        session: AsyncSession,
        cache: CacheBackend,
        settings: SettingsService,
    ) -> None:
        self._session = session
        self._cache = cache
        self._settings = settings

    async def is_active(self, chat_id: int) -> bool:
        """Действует ли сейчас тревога."""
        return await self._cache.get(chat_key(ChatEntity.RAID, chat_id)) is not None

    async def action_for(self, chat_id: int) -> str:
        """Что применять к входящим во время тревоги."""
        stored = await self._cache.get(chat_key(ChatEntity.RAID, chat_id))
        if isinstance(stored, str):
            return stored
        return str(await self._settings.get(chat_id, "antiraid.action"))

    async def register_join(self, chat_id: int) -> RaidStatus:
        """Учесть вход и решить, не начался ли налёт."""
        if not await self._settings.get(chat_id, "antiraid.enabled"):
            return RaidStatus(active=False)

        if await self.is_active(chat_id):
            return RaidStatus(
                active=True, action=await self.action_for(chat_id)
            )

        window = int(await self._settings.get(chat_id, "antiraid.window"))
        limit = int(await self._settings.get(chat_id, "antiraid.join_limit"))
        if window <= 0 or limit <= 0:
            return RaidStatus(active=False)

        joins = await self._cache.incr(chat_key(ChatEntity.RAID_COUNTER, chat_id), ttl=window)
        if joins < limit:
            return RaidStatus(active=False, joins=joins)

        action = await self.activate(chat_id, joins=joins)
        return RaidStatus(active=True, joins=joins, just_started=True, action=action)

    async def activate(self, chat_id: int, *, joins: int = 0, manual: bool = False) -> str:
        """Включить тревогу и записать событие."""
        action = str(await self._settings.get(chat_id, "antiraid.action"))
        duration = int(await self._settings.get(chat_id, "antiraid.duration"))

        # Срок жизни записи и есть срок тревоги: снимать её вручную не
        # обязательно, и перезапуск бота её не продлевает.
        await self._cache.set(chat_key(ChatEntity.RAID, chat_id), action, ttl=duration)

        self._session.add(
            RaidEvent(chat_id=chat_id, joins=joins, action=action, manual=manual)
        )
        log.warning(
            "включена защита от налёта",
            extra={"chat_id": chat_id, "joins": joins, "action": action,
                   "manual": manual, "duration": duration},
        )
        return action

    async def deactivate(self, chat_id: int) -> bool:
        """Снять тревогу досрочно."""
        if not await self.is_active(chat_id):
            return False

        await self._cache.delete(chat_key(ChatEntity.RAID, chat_id))
        await self._cache.delete(chat_key(ChatEntity.RAID_COUNTER, chat_id))
        log.info("защита от налёта снята", extra={"chat_id": chat_id})
        return True
