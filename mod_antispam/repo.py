"""Доступ к данным антиспама."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mod_antispam.models import ForbiddenWord, ForwardAllowance


class WordRepository:
    """Список запрещённых слов чата."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_words(self, chat_id: int) -> list[str]:
        stmt = select(ForbiddenWord.word).where(ForbiddenWord.chat_id == chat_id)
        return list((await self._session.execute(stmt)).scalars())

    async def add(self, chat_id: int, word: str, actor_id: int | None) -> bool:
        """Добавить слово. Возвращает ``False``, если оно уже в списке."""
        stmt = (
            insert(ForbiddenWord)
            .values(chat_id=chat_id, word=word.lower().strip(), added_by=actor_id)
            .on_conflict_do_nothing(index_elements=[ForbiddenWord.chat_id, ForbiddenWord.word])
            .returning(ForbiddenWord.id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def remove(self, chat_id: int, word: str) -> bool:
        result = await self._session.execute(
            delete(ForbiddenWord).where(
                ForbiddenWord.chat_id == chat_id, ForbiddenWord.word == word.lower().strip()
            )
        )
        return bool(result.rowcount)


class ForwardRepository:
    """Белый список источников пересылок."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_sources(self, chat_id: int) -> set[tuple[str, int]]:
        stmt = select(ForwardAllowance.source_type, ForwardAllowance.source_id).where(
            ForwardAllowance.chat_id == chat_id
        )
        return {(row[0], row[1]) for row in (await self._session.execute(stmt)).all()}

    async def list_all(self, chat_id: int) -> list[ForwardAllowance]:
        stmt = (
            select(ForwardAllowance)
            .where(ForwardAllowance.chat_id == chat_id)
            .order_by(ForwardAllowance.created_at)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def allow(
        self,
        chat_id: int,
        source_type: str,
        source_id: int,
        title: str | None,
        actor_id: int | None,
    ) -> bool:
        stmt = (
            insert(ForwardAllowance)
            .values(
                chat_id=chat_id,
                source_type=source_type,
                source_id=source_id,
                title=title,
                added_by=actor_id,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ForwardAllowance.chat_id,
                    ForwardAllowance.source_type,
                    ForwardAllowance.source_id,
                ]
            )
            .returning(ForwardAllowance.id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def deny(self, chat_id: int, source_id: int) -> bool:
        result = await self._session.execute(
            delete(ForwardAllowance).where(
                ForwardAllowance.chat_id == chat_id, ForwardAllowance.source_id == source_id
            )
        )
        return bool(result.rowcount)
