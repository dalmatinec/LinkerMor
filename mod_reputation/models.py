"""Репутация участников и история её изменений (ТЗ §11).

Текущее значение и история разделены намеренно: значение читается на
каждом показе профиля, а история нужна редко, но растёт быстро. Держать
их в одной таблице значило бы считать сумму по всем записям при каждом
обращении.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class Reputation(Base, TimestampMixin):
    """Текущая репутация участника в конкретном чате."""

    __tablename__ = "reputation"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        # Топ участников чата.
        Index("ix_reputation_top", "chat_id", text("value DESC")),
    )

    def __repr__(self) -> str:
        return f"<Reputation chat={self.chat_id} user={self.user_id} value={self.value}>"


class ReputationChange(Base):
    """Запись об изменении репутации.

    Хранится кто, кому, сколько и почему — чтобы спор о справедливости
    решался фактами, а не памятью участников.
    """

    __tablename__ = "reputation_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)

    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    value_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="message")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # История одного участника от свежих к старым.
        Index("ix_reputation_history_user", "chat_id", "user_id", "created_at"),
        # Ограничение частоты: сколько раз этот человек уже дарил сегодня.
        Index("ix_reputation_history_actor", "chat_id", "actor_id", "created_at"),
    )
