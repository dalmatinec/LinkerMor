"""Запросы статистики."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mod_chats.models import ChatMember
from mod_moderation.models import Punishment, Warning
from mod_stats.models import DailyActivity


class StatsRepository:
    """Сбор и чтение статистики чата."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_message(self, chat_id: int, user_id: int) -> None:
        """Учесть сообщение в дневной активности.

        Выполняется одним запросом: при всплеске активности чтение с
        последующей записью теряло бы сообщения.
        """
        stmt = (
            insert(DailyActivity)
            .values(chat_id=chat_id, user_id=user_id, day=datetime.now(UTC).date(), messages=1)
            .on_conflict_do_update(
                index_elements=[
                    DailyActivity.chat_id,
                    DailyActivity.user_id,
                    DailyActivity.day,
                ],
                set_={"messages": DailyActivity.messages + 1},
            )
        )
        await self._session.execute(stmt)

    async def messages_since(self, chat_id: int, since: date) -> int:
        stmt = select(func.coalesce(func.sum(DailyActivity.messages), 0)).where(
            DailyActivity.chat_id == chat_id, DailyActivity.day >= since
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def active_members_since(self, chat_id: int, since: date) -> int:
        stmt = select(func.count(func.distinct(DailyActivity.user_id))).where(
            DailyActivity.chat_id == chat_id, DailyActivity.day >= since
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def top_members(
        self, chat_id: int, since: date, limit: int = 5
    ) -> list[tuple[int, int]]:
        stmt = (
            select(DailyActivity.user_id, func.sum(DailyActivity.messages).label("total"))
            .where(DailyActivity.chat_id == chat_id, DailyActivity.day >= since)
            .group_by(DailyActivity.user_id)
            .order_by(func.sum(DailyActivity.messages).desc())
            .limit(limit)
        )
        return [(row[0], int(row[1])) for row in (await self._session.execute(stmt)).all()]

    async def daily_series(self, chat_id: int, days: int = 7) -> list[tuple[date, int]]:
        """Сообщения по дням — для наглядного графика в сводке."""
        since = datetime.now(UTC).date() - timedelta(days=days - 1)
        stmt = (
            select(DailyActivity.day, func.sum(DailyActivity.messages))
            .where(DailyActivity.chat_id == chat_id, DailyActivity.day >= since)
            .group_by(DailyActivity.day)
            .order_by(DailyActivity.day)
        )
        found = {row[0]: int(row[1]) for row in (await self._session.execute(stmt)).all()}
        return [(since + timedelta(days=offset), found.get(since + timedelta(days=offset), 0))
                for offset in range(days)]

    async def members_total(self, chat_id: int) -> int:
        stmt = select(func.count()).where(ChatMember.chat_id == chat_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def staff_total(self, chat_id: int) -> int:
        from core.constants import Role

        stmt = select(func.count()).where(
            ChatMember.chat_id == chat_id, ChatMember.role > int(Role.MEMBER)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def new_members_since(self, chat_id: int, since: datetime) -> int:
        stmt = select(func.count()).where(
            ChatMember.chat_id == chat_id, ChatMember.joined_at >= since
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def punishments_since(self, chat_id: int, since: datetime) -> dict[str, int]:
        stmt = (
            select(Punishment.type, func.count())
            .where(Punishment.chat_id == chat_id, Punishment.created_at >= since)
            .group_by(Punishment.type)
        )
        return {row[0]: int(row[1]) for row in (await self._session.execute(stmt)).all()}

    async def filter_punishments_since(self, chat_id: int, since: datetime) -> int:
        stmt = select(func.count()).where(
            Punishment.chat_id == chat_id,
            Punishment.created_at >= since,
            Punishment.source == "filter",
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def warnings_since(self, chat_id: int, since: datetime) -> int:
        stmt = select(func.count()).where(
            Warning.chat_id == chat_id, Warning.created_at >= since
        )
        return int((await self._session.execute(stmt)).scalar_one())
