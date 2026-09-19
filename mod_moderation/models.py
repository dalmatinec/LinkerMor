"""Наказания и предупреждения.

Записи не удаляются: снятый бан помечается неактивным, а снятое
предупреждение — отозванным. История нужна и для разбора спорных случаев,
и для статистики в панели владельца.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class PunishmentType(StrEnum):
    """Вид наказания."""

    BAN = "ban"
    MUTE = "mute"
    KICK = "kick"  # исключение с правом вернуться


class PunishmentSource(StrEnum):
    """Что привело к наказанию — важно для разбора и статистики."""

    MANUAL = "manual"  # команда администратора
    WARN = "warn"  # исчерпаны предупреждения
    FILTER = "filter"  # сработало правило антиспама
    CAPTCHA = "captcha"  # не пройдена проверка при входе


class Punishment(Base, TimestampMixin):
    """Выданное наказание.

    Telegram снимает временные ограничения сам, но собственная запись нужна:
    по ней строится история, показывается срок и работает снятие вручную.
    """

    __tablename__ = "punishments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False
    )
    #: Идентификатор наказанного. Для сообщений от имени канала это канал,
    #: поэтому внешнего ключа на users здесь нет.
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_chat_target: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    type: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PunishmentSource.MANUAL
    )
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text)

    #: Когда наказание заканчивается. NULL — бессрочное.
    until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        # Поиск действующего наказания конкретного человека в чате.
        Index("ix_punishments_active", "chat_id", "user_id", postgresql_where=text("is_active")),
        # Фоновая задача ищет истёкшие наказания по сроку.
        Index("ix_punishments_until", "until", postgresql_where=text("is_active")),
        # История чата в панели.
        Index("ix_punishments_chat_created", "chat_id", "created_at"),
    )


class Warning(Base, TimestampMixin):
    """Предупреждение участнику.

    Предупреждения истекают: нарушение полугодовой давности не должно
    вечно приближать человека к бану.
    """

    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text)

    #: Когда предупреждение перестаёт учитываться. NULL — бессрочное.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        # Подсчёт действующих предупреждений человека в чате.
        Index(
            "ix_warnings_active",
            "chat_id",
            "user_id",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_warnings_chat_created", "chat_id", "created_at"),
    )

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)


