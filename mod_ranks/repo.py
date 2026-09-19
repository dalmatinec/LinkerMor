"""Доступ к рангам."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mod_ranks.models import Rank, UserRank


class RankRepository:
    """Ступени чата и достигнутые участниками ранги."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_ranks(self, chat_id: int) -> list[Rank]:
        """Ранги чата по возрастанию порога."""
        stmt = select(Rank).where(Rank.chat_id == chat_id).order_by(Rank.threshold)
        return list((await self._session.execute(stmt)).scalars())

    async def add(self, chat_id: int, name: str, threshold: int) -> Rank:
        rank = Rank(chat_id=chat_id, name=name, threshold=threshold)
        self._session.add(rank)
        await self._session.flush()
        return rank

    async def get_by_name(self, chat_id: int, name: str) -> Rank | None:
        stmt = select(Rank).where(Rank.chat_id == chat_id, Rank.name == name)
        return (await self._session.execute(stmt)).scalars().first()

    async def delete_by_name(self, chat_id: int, name: str) -> bool:
        rank = await self.get_by_name(chat_id, name)
        if rank is None:
            return False
        await self._session.execute(delete(Rank).where(Rank.id == rank.id))
        return True

    async def user_rank_id(self, chat_id: int, user_id: int) -> int | None:
        stmt = select(UserRank.rank_id).where(
            UserRank.chat_id == chat_id, UserRank.user_id == user_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def set_user_rank(self, chat_id: int, user_id: int, rank_id: int | None) -> None:
        stmt = (
            insert(UserRank)
            .values(chat_id=chat_id, user_id=user_id, rank_id=rank_id)
            .on_conflict_do_update(
                index_elements=[UserRank.chat_id, UserRank.user_id],
                set_={"rank_id": rank_id},
            )
        )
        await self._session.execute(stmt)
