"""Доступ к триггерам и сохранённым сообщениям."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mod_triggers.models import ContentKind, MessageContent, Trigger


class ContentRepository:
    """Сохранённые сообщения: ответы триггеров, приветствия, капча."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        kind: ContentKind | str,
        text: str | None,
        entities: list[dict[str, Any]] | None = None,
        file_id: str | None = None,
        file_unique_id: str | None = None,
        keyboard: list[Any] | None = None,
    ) -> MessageContent:
        content = MessageContent(
            kind=kind,
            text=text,
            entities=entities or [],
            file_id=file_id,
            file_unique_id=file_unique_id,
            keyboard=keyboard or [],
        )
        self._session.add(content)
        await self._session.flush()
        return content

    async def get(self, content_id: int) -> MessageContent | None:
        return await self._session.get(MessageContent, content_id)

    async def delete(self, content_id: int) -> None:
        await self._session.execute(
            delete(MessageContent).where(MessageContent.id == content_id)
        )


class TriggerRepository:
    """Триггеры конкретного чата."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        chat_id: int,
        key: str,
        display_key: str,
        match_type: str,
        content: MessageContent,
        created_by: int | None,
        cooldown: int = 0,
    ) -> Trigger:
        """Создать триггер.

        Сообщение-ответ передаётся объектом, а не идентификатором: иначе
        связь осталась бы незаполненной, и первое же обращение к ней
        привело бы к синхронной подгрузке внутри асинхронного кода.
        """
        trigger = Trigger(
            chat_id=chat_id,
            key=key,
            display_key=display_key,
            match_type=match_type,
            content=content,
            created_by=created_by,
            cooldown=cooldown,
        )
        self._session.add(trigger)
        await self._session.flush()
        return trigger

    async def get_by_key(self, chat_id: int, key: str) -> Trigger | None:
        stmt = select(Trigger).where(Trigger.chat_id == chat_id, Trigger.key == key)
        return (await self._session.execute(stmt)).scalars().first()

    async def get(self, chat_id: int, trigger_id: int) -> Trigger | None:
        """Триггер по идентификатору строго в пределах своего чата."""
        stmt = select(Trigger).where(Trigger.chat_id == chat_id, Trigger.id == trigger_id)
        return (await self._session.execute(stmt)).scalars().first()

    async def list_all(self, chat_id: int) -> list[Trigger]:
        stmt = (
            select(Trigger)
            .where(Trigger.chat_id == chat_id)
            .order_by(Trigger.display_key)
        )
        return list((await self._session.execute(stmt)).unique().scalars())

    async def list_enabled(self, chat_id: int) -> list[Trigger]:
        stmt = select(Trigger).where(Trigger.chat_id == chat_id, Trigger.is_enabled.is_(True))
        return list((await self._session.execute(stmt)).unique().scalars())

    async def delete(self, chat_id: int, key: str) -> int:
        """Удалить триггер вместе с его сообщением-ответом."""
        trigger = await self.get_by_key(chat_id, key)
        if trigger is None:
            return 0

        content_id = trigger.content_id
        await self._session.execute(delete(Trigger).where(Trigger.id == trigger.id))
        await ContentRepository(self._session).delete(content_id)
        return 1

    async def set_enabled(self, chat_id: int, key: str, enabled: bool) -> bool:
        result = await self._session.execute(
            update(Trigger)
            .where(Trigger.chat_id == chat_id, Trigger.key == key)
            .values(is_enabled=enabled, updated_at=func.now())
        )
        return bool(result.rowcount)

    async def register_hit(self, trigger_id: int) -> None:
        """Атомарно отметить срабатывание: счётчик нужен статистике."""
        await self._session.execute(
            update(Trigger).where(Trigger.id == trigger_id).values(hits=Trigger.hits + 1)
        )

    async def count(self, chat_id: int) -> int:
        stmt = select(func.count()).where(Trigger.chat_id == chat_id)
        return int((await self._session.execute(stmt)).scalar_one())
