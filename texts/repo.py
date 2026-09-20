"""Доступ к таблицам текстов."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from texts.entities import EntityText
from texts.models import ChatText, GlobalText


class TextRepository:
    """Чтение и запись переопределённых текстов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_chat_texts(self, chat_id: int, lang: str) -> dict[str, EntityText]:
        """Все тексты чата одним запросом."""
        stmt = select(ChatText.key, ChatText.text, ChatText.entities).where(
            ChatText.chat_id == chat_id, ChatText.lang == lang
        )
        rows = (await self._session.execute(stmt)).all()
        return {key: EntityText.from_storage(text, entities) for key, text, entities in rows}

    async def load_global_texts(self, lang: str) -> dict[str, EntityText]:
        stmt = select(GlobalText.key, GlobalText.text, GlobalText.entities).where(
            GlobalText.lang == lang
        )
        rows = (await self._session.execute(stmt)).all()
        return {key: EntityText.from_storage(text, entities) for key, text, entities in rows}

    async def upsert_chat_text(
        self, chat_id: int, key: str, lang: str, value: EntityText, actor_id: int | None
    ) -> None:
        stmt = (
            insert(ChatText)
            .values(
                chat_id=chat_id,
                key=key,
                lang=lang,
                text=value.text,
                entities=value.entities_json(),
                updated_by=actor_id,
            )
            .on_conflict_do_update(
                index_elements=[ChatText.chat_id, ChatText.key, ChatText.lang],
                set_={
                    "text": value.text,
                    "entities": value.entities_json(),
                    "updated_by": actor_id,
                    "updated_at": func.now(),
                },
            )
        )
        await self._session.execute(stmt)

    async def upsert_global_text(
        self, key: str, lang: str, value: EntityText, actor_id: int | None
    ) -> None:
        stmt = (
            insert(GlobalText)
            .values(
                key=key,
                lang=lang,
                text=value.text,
                entities=value.entities_json(),
                updated_by=actor_id,
            )
            .on_conflict_do_update(
                index_elements=[GlobalText.key, GlobalText.lang],
                set_={
                    "text": value.text,
                    "entities": value.entities_json(),
                    "updated_by": actor_id,
                    "updated_at": func.now(),
                },
            )
        )
        await self._session.execute(stmt)

    async def delete_chat_text(self, chat_id: int, key: str, lang: str) -> None:
        await self._session.execute(
            delete(ChatText).where(
                ChatText.chat_id == chat_id, ChatText.key == key, ChatText.lang == lang
            )
        )
