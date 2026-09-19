"""Доступ к данным модерации."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mod_chats.models import ChatMember
from mod_moderation.models import Punishment, PunishmentSource, PunishmentType, Warning


class PunishmentRepository:
    """История и текущее состояние наказаний."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        chat_id: int,
        user_id: int,
        type_: PunishmentType,
        actor_id: int | None,
        reason: str | None,
        until: datetime | None,
        source: PunishmentSource = PunishmentSource.MANUAL,
        is_chat_target: bool = False,
    ) -> Punishment:
        """Записать наказание, погасив предыдущее того же вида.

        Повторный бан не должен оставлять в базе две действующие записи:
        иначе снятие одной оставит человека наказанным по второй.
        """
        await self.deactivate(chat_id, user_id, type_)

        punishment = Punishment(
            chat_id=chat_id,
            user_id=user_id,
            type=type_,
            source=source,
            actor_id=actor_id,
            reason=reason,
            until=until,
            is_chat_target=is_chat_target,
            is_active=True,
        )
        self._session.add(punishment)
        await self._session.flush()
        return punishment

    async def active(
        self, chat_id: int, user_id: int, type_: PunishmentType
    ) -> Punishment | None:
        stmt = select(Punishment).where(
            Punishment.chat_id == chat_id,
            Punishment.user_id == user_id,
            Punishment.type == type_,
            Punishment.is_active.is_(True),
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def deactivate(
        self,
        chat_id: int,
        user_id: int,
        type_: PunishmentType,
        revoked_by: int | None = None,
    ) -> int:
        """Снять действующие наказания этого вида. Возвращает их количество."""
        stmt = (
            update(Punishment)
            .where(
                Punishment.chat_id == chat_id,
                Punishment.user_id == user_id,
                Punishment.type == type_,
                Punishment.is_active.is_(True),
            )
            .values(is_active=False, revoked_at=datetime.now(UTC), revoked_by=revoked_by)
        )
        return (await self._session.execute(stmt)).rowcount

    async def expired(self, limit: int = 100) -> list[Punishment]:
        """Наказания, срок которых истёк, но запись ещё активна.

        Telegram снимает ограничение сам; задача лишь приводит собственное
        состояние в соответствие.
        """
        stmt = (
            select(Punishment)
            .where(
                Punishment.is_active.is_(True),
                Punishment.until.isnot(None),
                Punishment.until <= datetime.now(UTC),
            )
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def history(self, chat_id: int, user_id: int | None = None, limit: int = 20) -> list:
        stmt = select(Punishment).where(Punishment.chat_id == chat_id)
        if user_id is not None:
            stmt = stmt.where(Punishment.user_id == user_id)
        stmt = stmt.order_by(Punishment.created_at.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars())


class WarningRepository:
    """Предупреждения и их подсчёт."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_member(self, chat_id: int, user_id: int) -> None:
        """Заблокировать строку участника до конца транзакции.

        Два администратора могут выдать предупреждение одновременно. Без
        блокировки оба посчитают одинаковое число действующих и оба решат,
        что порог не достигнут — наказание не сработает. Блокировка строки
        выстраивает такие операции в очередь.
        """
        stmt = (
            select(ChatMember.user_id)
            .where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
            .with_for_update()
        )
        await self._session.execute(stmt)

    async def add(
        self,
        *,
        chat_id: int,
        user_id: int,
        actor_id: int | None,
        reason: str | None,
        expires_at: datetime | None,
    ) -> Warning:
        warning = Warning(
            chat_id=chat_id,
            user_id=user_id,
            actor_id=actor_id,
            reason=reason,
            expires_at=expires_at,
        )
        self._session.add(warning)
        await self._session.flush()
        return warning

    async def count_active(self, chat_id: int, user_id: int) -> int:
        """Сколько предупреждений действует прямо сейчас."""
        now = datetime.now(UTC)
        stmt = select(func.count()).where(
            Warning.chat_id == chat_id,
            Warning.user_id == user_id,
            Warning.revoked_at.is_(None),
            (Warning.expires_at.is_(None)) | (Warning.expires_at > now),
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def revoke_last(self, chat_id: int, user_id: int, revoked_by: int | None) -> bool:
        """Снять последнее действующее предупреждение."""
        now = datetime.now(UTC)
        stmt = (
            select(Warning.id)
            .where(
                Warning.chat_id == chat_id,
                Warning.user_id == user_id,
                Warning.revoked_at.is_(None),
                (Warning.expires_at.is_(None)) | (Warning.expires_at > now),
            )
            .order_by(Warning.created_at.desc())
            .limit(1)
        )
        warning_id = (await self._session.execute(stmt)).scalar_one_or_none()
        if warning_id is None:
            return False

        await self._session.execute(
            update(Warning)
            .where(Warning.id == warning_id)
            .values(revoked_at=now, revoked_by=revoked_by)
        )
        return True

    async def revoke_all(self, chat_id: int, user_id: int, revoked_by: int | None) -> int:
        """Снять все действующие предупреждения.

        Вызывается после наказания за превышение порога: счёт начинается
        заново, иначе следующее же предупреждение снова его превысит.
        """
        now = datetime.now(UTC)
        stmt = (
            update(Warning)
            .where(
                Warning.chat_id == chat_id,
                Warning.user_id == user_id,
                Warning.revoked_at.is_(None),
                (Warning.expires_at.is_(None)) | (Warning.expires_at > now),
            )
            .values(revoked_at=now, revoked_by=revoked_by)
        )
        return (await self._session.execute(stmt)).rowcount

    async def list_active(self, chat_id: int, user_id: int) -> list[Warning]:
        now = datetime.now(UTC)
        stmt = (
            select(Warning)
            .where(
                Warning.chat_id == chat_id,
                Warning.user_id == user_id,
                Warning.revoked_at.is_(None),
                (Warning.expires_at.is_(None)) | (Warning.expires_at > now),
            )
            .order_by(Warning.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars())
