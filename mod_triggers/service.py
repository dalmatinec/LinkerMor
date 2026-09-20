"""Логика триггеров (ТЗ §8).

Правила срабатывания держатся в кеше: они проверяются на каждом сообщении
чата, и поход в базу за ними был бы самым частым запросом приложения.
Кеш сбрасывается при любом изменении триггеров этого чата.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from core.constants import Role
from core.errors import LinkerMorError
from core.logging import get_logger
from mod_triggers.content import extract
from mod_triggers.matcher import (
    TriggerRule,
    find_match,
    normalize,
    validate_pattern,
)
from mod_triggers.models import ContentKind, MatchType, Trigger
from mod_triggers.repo import ContentRepository, TriggerRepository
from texts.entities import EntityText

log = get_logger(__name__)

RULES_CACHE_TTL = 600

#: Больше триггеров на чат заводить незачем: каждое сообщение проверяется
#: по всему списку, и разрастание превращается в задержку для участников.
MAX_TRIGGERS_PER_CHAT = 200


class TriggerLimitReached(LinkerMorError):
    """В чате слишком много триггеров."""

    text_key = "trigger_limit"


class TriggerExists(LinkerMorError):
    """Такое ключевое слово уже занято."""

    text_key = "trigger_exists"


class TriggerService:
    """Создание, удаление и поиск триггеров."""

    def __init__(self, session: AsyncSession, cache: CacheBackend) -> None:
        self._session = session
        self._cache = cache
        self._triggers = TriggerRepository(session)
        self._contents = ContentRepository(session)

    # ─── Изменение ───────────────────────────────────────────────────────────

    async def add(
        self,
        chat_id: int,
        key: str,
        *,
        source: Message | None = None,
        text: str | None = None,
        match_type: str = MatchType.WORD,
        actor_id: int | None = None,
        actor_role: Role = Role.CHAT_ADMIN,
    ) -> Trigger:
        """Создать триггер из сообщения-ответа или из текста.

        Raises:
            TriggerPatternError: ключ не годится.
            TriggerExists: ключ уже занят в этом чате.
            TriggerLimitReached: превышен предел триггеров на чат.
            PermissionDenied: регулярное выражение заводит не владелец.
        """
        if match_type == MatchType.REGEX and actor_role < Role.BOT_OWNER:
            from core.errors import PermissionDenied

            # Регулярное выражение способно занять процессор надолго,
            # поэтому такие триггеры заводит только владелец бота.
            raise PermissionDenied("Регулярные выражения доступны владельцу бота")

        validate_pattern(key, match_type)
        normalized = key if match_type == MatchType.REGEX else normalize(key)

        if await self._triggers.get_by_key(chat_id, normalized) is not None:
            raise TriggerExists("Такой триггер уже есть", trigger=key)
        if await self._triggers.count(chat_id) >= MAX_TRIGGERS_PER_CHAT:
            raise TriggerLimitReached("Достигнут предел триггеров", count=MAX_TRIGGERS_PER_CHAT)

        fields = (
            extract(source)
            if source is not None
            else {"kind": ContentKind.TEXT, "text": text, "entities": [], "file_id": None,
                  "file_unique_id": None}
        )
        content = await self._contents.create(**fields)

        trigger = await self._triggers.create(
            chat_id=chat_id,
            key=normalized,
            display_key=key.strip()[:128],
            match_type=match_type,
            content=content,
            created_by=actor_id,
        )
        await self.invalidate(chat_id)

        log.info(
            "триггер создан",
            extra={"chat_id": chat_id, "trigger": normalized, "kind": fields["kind"],
                   "actor": actor_id},
        )
        return trigger

    async def remove(self, chat_id: int, key: str) -> bool:
        removed = await self._triggers.delete(chat_id, normalize(key))
        if removed:
            await self.invalidate(chat_id)
            log.info("триггер удалён", extra={"chat_id": chat_id, "trigger": key})
        return bool(removed)

    async def set_enabled(self, chat_id: int, key: str, enabled: bool) -> bool:
        changed = await self._triggers.set_enabled(chat_id, normalize(key), enabled)
        if changed:
            await self.invalidate(chat_id)
        return changed

    async def list_all(self, chat_id: int) -> list[Trigger]:
        return await self._triggers.list_all(chat_id)

    # ─── Поиск ───────────────────────────────────────────────────────────────

    async def rules(self, chat_id: int) -> list[TriggerRule]:
        """Правила чата, пригодные для сопоставления."""
        key = chat_key(ChatEntity.TRIGGERS, chat_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        rules = [
            TriggerRule(
                id=trigger.id,
                key=trigger.key,
                match_type=trigger.match_type,
                cooldown=trigger.cooldown,
            )
            for trigger in await self._triggers.list_enabled(chat_id)
        ]
        await self._cache.set(key, rules, ttl=RULES_CACHE_TTL)
        return rules

    async def find(self, chat_id: int, message_text: str) -> Trigger | None:
        """Найти сработавший триггер с учётом паузы между ответами."""
        rules = await self.rules(chat_id)
        if not rules:
            return None

        rule = find_match(rules, message_text)
        if rule is None:
            return None

        if rule.cooldown and await self._on_cooldown(chat_id, rule):
            log.debug("триггер на паузе", extra={"chat_id": chat_id, "trigger": rule.key})
            return None

        trigger = await self._triggers.get(chat_id, rule.id)
        if trigger is None:
            # Триггер удалили, пока правила лежали в кеше.
            await self.invalidate(chat_id)
            return None

        await self._triggers.register_hit(trigger.id)
        return trigger

    async def _on_cooldown(self, chat_id: int, rule: TriggerRule) -> bool:
        key = chat_key(ChatEntity.TRIGGER_COOLDOWN, chat_id, rule.id)
        if await self._cache.get(key) is not None:
            return True
        await self._cache.set(key, True, ttl=rule.cooldown)
        return False

    async def invalidate(self, chat_id: int) -> None:
        """Сбросить правила этого чата, не затрагивая остальные."""
        await self._cache.delete(chat_key(ChatEntity.TRIGGERS, chat_id))

    @staticmethod
    def response_of(trigger: Trigger) -> tuple[str, EntityText, str | None, list[Any]]:
        """Разложить ответ триггера на части для отправки."""
        content = trigger.content
        body = EntityText.from_storage(content.text or "", content.entities)
        return content.kind, body, content.file_id, content.keyboard
