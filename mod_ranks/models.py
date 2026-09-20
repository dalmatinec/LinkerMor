"""Ранги участников (ТЗ §12).

Метрика ранга настраивается для каждого чата: где-то ценится репутация,
где-то активность. Поэтому порог хранится числом без привязки к смыслу, а
сравнивается с тем значением, которое выбрал чат.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class RankMetric(StrEnum):
    """По какому показателю считается ранг."""

    REPUTATION = "reputation"
    MESSAGES = "messages"
    SUM = "sum"  # репутация плюс сообщения


class Rank(Base, TimestampMixin):
    """Ступень в чате: название и порог."""

    __tablename__ = "ranks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        # Два ранга с одним порогом сделали бы результат неопределённым.
        UniqueConstraint("chat_id", "threshold", name="uq_ranks_chat_threshold"),
        UniqueConstraint("chat_id", "name", name="uq_ranks_chat_name"),
        Index("ix_ranks_chat_threshold", "chat_id", "threshold"),
    )

    def __repr__(self) -> str:
        return f"<Rank {self.chat_id}:{self.name}@{self.threshold}>"


class UserRank(Base):
    """Ранг, достигнутый участником.

    Хранится, чтобы заметить переход: без этого бот не отличил бы
    «человек только что получил ранг» от «человек давно его имеет» и
    поздравлял бы при каждом сообщении.
    """

    __tablename__ = "user_ranks"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rank_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ranks.id", ondelete="SET NULL")
    )
    achieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
