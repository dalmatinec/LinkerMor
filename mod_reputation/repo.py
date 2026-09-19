"""Доступ к данным репутации."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mod_reputation.models import Reputation, ReputationChange


class ReputationRepository:
    """Чтение и изменение репутации."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def value_of(self, chat_id: int, user_id: int) -> int:
        stmt = select(Reputation.value).where(
            Reputation.chat_id == chat_id, Reputation.user_id == user_id
        )
        return int((await self._session.execute(stmt)).scalar_one_or_none() or 0)

    async def apply(self, chat_id: int, user_id: int, delta: int) -> int:
        """Изменить репутацию одним запросом и вернуть новое значение.

        Прибавление выполняется на стороне базы, без чтения предыдущего
        значения: два человека могут поблагодарить одновременно, и
        промежуточный результат потеряться не должен.
        """
        stmt = (
            insert(Reputation)
            .values(chat_id=chat_id, user_id=user_id, value=delta)
            .on_conflict_do_update(
                index_elements=[Reputation.chat_id, Reputation.user_id],
                set_={"value": Reputation.value + delta, "updated_at": func.now()},
            )
            .returning(Reputation.value)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def record(
        self,
        *,
        chat_id: int,
        user_id: int,
        actor_id: int | None,
        delta: int,
        value_after: int,
        reason: str | None,
        source: str = "message",
    ) -> None:
        self._session.add(
            ReputationChange(
                chat_id=chat_id,
                user_id=user_id,
                actor_id=actor_id,
                delta=delta,
                value_after=value_after,
                reason=reason,
                source=source,
            )
        )

    async def top(self, chat_id: int, limit: int = 10) -> list[tuple[int, int]]:
        """Участники с наибольшей репутацией."""
        stmt = (
            select(Reputation.user_id, Reputation.value)
            .where(Reputation.chat_id == chat_id, Reputation.value != 0)
            .order_by(Reputation.value.desc())
            .limit(limit)
        )
        return [(user_id, value) for user_id, value in (await self._session.execute(stmt)).all()]

    async def position_of(self, chat_id: int, user_id: int) -> int:
        """Место участника в списке по репутации."""
        value = await self.value_of(chat_id, user_id)
        stmt = select(func.count()).where(
            Reputation.chat_id == chat_id, Reputation.value > value
        )
        return int((await self._session.execute(stmt)).scalar_one()) + 1

    async def history(self, chat_id: int, user_id: int, limit: int = 20) -> list:
        stmt = (
            select(ReputationChange)
            .where(ReputationChange.chat_id == chat_id, ReputationChange.user_id == user_id)
            .order_by(ReputationChange.created_at.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())

    # ─── Ограничения ─────────────────────────────────────────────────────────

    async def seconds_since_last(
        self, chat_id: int, actor_id: int, user_id: int
    ) -> float | None:
        """Сколько прошло с прошлого изменения этой же паре.

        Возвращает ``None``, если этот человек ещё не менял репутацию
        именно этому участнику.
        """
        stmt = (
            select(ReputationChange.created_at)
            .where(
                ReputationChange.chat_id == chat_id,
                ReputationChange.actor_id == actor_id,
                ReputationChange.user_id == user_id,
            )
            .order_by(ReputationChange.created_at.desc())
            .limit(1)
        )
        last = (await self._session.execute(stmt)).scalar_one_or_none()
        if last is None:
            return None
        return (datetime.now(UTC) - last).total_seconds()

    async def given_last_day(self, chat_id: int, actor_id: int) -> int:
        """Сколько раз человек менял репутацию за последние сутки."""
        since = datetime.now(UTC) - timedelta(days=1)
        stmt = select(func.count()).where(
            ReputationChange.chat_id == chat_id,
            ReputationChange.actor_id == actor_id,
            ReputationChange.created_at >= since,
        )
        return int((await self._session.execute(stmt)).scalar_one())
