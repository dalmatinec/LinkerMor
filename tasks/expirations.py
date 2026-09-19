"""Приведение записей о наказаниях в соответствие с реальностью.

Временные ограничения Telegram снимает сам по истечении срока. Собственные
записи об этом не узнают, поэтому их закрывает фоновая задача — иначе
панель показывала бы давно истёкшие муты как действующие.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.logging import get_logger
from database.session import session_scope
from mod_moderation.repo import PunishmentRepository

log = get_logger(__name__)

#: Как часто сверять сроки. Минута — достаточная точность для наказаний.
EXPIRATION_INTERVAL = 60.0


async def close_expired_punishments(session: AsyncSession) -> int:
    """Закрыть наказания, срок которых истёк."""
    repo = PunishmentRepository(session)
    expired = await repo.expired()

    for punishment in expired:
        punishment.is_active = False

    if expired:
        log.info("закрыты истёкшие наказания", extra={"count": len(expired)})
    return len(expired)


def make_expiration_task(session_factory: async_sessionmaker[AsyncSession]):
    """Собрать задачу для планировщика."""

    async def run() -> None:
        async with session_scope(session_factory) as session:
            await close_expired_punishments(session)

    return run
