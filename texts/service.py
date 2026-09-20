"""Единая точка доступа к текстам (ТЗ §13).

Текст ищется по цепочке: текст чата → глобальный текст → значение по
умолчанию из реестра. Пустых мест не остаётся никогда, даже если ничего не
настроено.

Сервис возвращает готовый ``EntityText``: текст вместе с форматированием и
подставленными значениями. Хендлеру остаётся только отправить его.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import ChatEntity, GlobalEntity, chat_key, global_key
from core.constants import DEFAULT_LANGUAGE
from core.errors import SettingValidationError
from core.logging import get_logger
from texts.defs import TextRegistry
from texts.entities import EntityText
from texts.placeholders import Value, unknown_placeholders
from texts.repo import TextRepository

log = get_logger(__name__)

TEXTS_CACHE_TTL = 300


class TextService:
    """Чтение, изменение и подготовка текстов к отправке."""

    def __init__(
        self,
        session: AsyncSession,
        cache: CacheBackend,
        registry: TextRegistry,
        default_language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self._session = session
        self._cache = cache
        self._registry = registry
        self._default_language = default_language
        self._repo = TextRepository(session)

    # ─── Чтение ──────────────────────────────────────────────────────────────

    async def get(self, chat_id: int | None, key: str, lang: str | None = None) -> EntityText:
        """Текст без подстановки значений — для панели редактирования."""
        definition = self._registry.get(key)
        language = lang or self._default_language

        if chat_id is not None:
            chat_texts = await self._chat_texts(chat_id, language)
            if key in chat_texts:
                return chat_texts[key]

        global_texts = await self._global_texts(language)
        if key in global_texts:
            return global_texts[key]

        return EntityText(text=definition.default)

    async def render(
        self,
        chat_id: int | None,
        key: str,
        values: Mapping[str, Value] | None = None,
        lang: str | None = None,
    ) -> EntityText:
        """Текст с подставленными значениями — готов к отправке."""
        template = await self.get(chat_id, key, lang)
        return template.render(values or {})

    async def source_of(self, chat_id: int, key: str, lang: str | None = None) -> str:
        """Откуда взят текст: ``chat``, ``global`` или ``default``.

        Нужно панели редактирования, чтобы показать, переопределён ли текст.
        """
        language = lang or self._default_language
        if key in await self._chat_texts(chat_id, language):
            return "chat"
        if key in await self._global_texts(language):
            return "global"
        return "default"

    # ─── Изменение ───────────────────────────────────────────────────────────

    async def set_for_chat(
        self,
        chat_id: int,
        key: str,
        value: EntityText,
        actor_id: int | None = None,
        lang: str | None = None,
    ) -> EntityText:
        """Переопределить текст для одного чата.

        Raises:
            SettingValidationError: текст содержит неизвестный плейсхолдер.
        """
        self._registry.get(key)
        self._validate(key, value)
        language = lang or self._default_language

        await self._repo.upsert_chat_text(chat_id, key, language, value, actor_id)
        await self._invalidate_chat(chat_id, language)

        log.info(
            "текст чата изменён",
            extra={"chat_id": chat_id, "text_key": key, "actor": actor_id},
        )
        return value

    async def set_global(
        self,
        key: str,
        value: EntityText,
        actor_id: int | None = None,
        lang: str | None = None,
    ) -> EntityText:
        """Переопределить текст для всех чатов. Доступно владельцу бота."""
        self._registry.get(key)
        self._validate(key, value)
        language = lang or self._default_language

        await self._repo.upsert_global_text(key, language, value, actor_id)
        await self._invalidate_global(language)

        log.info("глобальный текст изменён", extra={"text_key": key, "actor": actor_id})
        return value

    async def reset_for_chat(
        self, chat_id: int, key: str, lang: str | None = None
    ) -> EntityText:
        """Убрать переопределение чата: текст вернётся к общему значению."""
        language = lang or self._default_language
        await self._repo.delete_chat_text(chat_id, key, language)
        await self._invalidate_chat(chat_id, language)
        return await self.get(chat_id, key, language)

    def _validate(self, key: str, value: EntityText) -> None:
        unknown = unknown_placeholders(value)
        if unknown:
            raise SettingValidationError(
                "Неизвестные плейсхолдеры: " + ", ".join(sorted(f"{{{n}}}" for n in unknown)),
                key=key,
                unknown=sorted(unknown),
            )

    # ─── Кеш ─────────────────────────────────────────────────────────────────

    async def _chat_texts(self, chat_id: int, lang: str) -> dict[str, EntityText]:
        key = chat_key(ChatEntity.TEXTS, chat_id, lang)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        texts = await self._repo.load_chat_texts(chat_id, lang)
        await self._cache.set(key, texts, ttl=TEXTS_CACHE_TTL)
        return texts

    async def _global_texts(self, lang: str) -> dict[str, EntityText]:
        key = global_key(GlobalEntity.GLOBAL_TEXTS, lang)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        texts = await self._repo.load_global_texts(lang)
        await self._cache.set(key, texts, ttl=TEXTS_CACHE_TTL)
        return texts

    async def _invalidate_chat(self, chat_id: int, lang: str) -> None:
        """Сбросить тексты одного чата, не затрагивая остальные."""
        await self._cache.delete(chat_key(ChatEntity.TEXTS, chat_id, lang))

    async def _invalidate_global(self, lang: str) -> None:
        """Сбросить глобальные тексты и кеш всех чатов.

        Глобальный текст виден каждому чату, который его не переопределил,
        поэтому кеш чатов тоже устаревает.
        """
        await self._cache.delete(global_key(GlobalEntity.GLOBAL_TEXTS, lang))
        await self._cache.delete_pattern(f"lm:v1:{ChatEntity.TEXTS.value}:*")
