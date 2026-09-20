"""История налётов на чат.

Состояние тревоги живёт в кеше и само истекает, а в базе остаётся запись
о случившемся: когда начался налёт, сколько человек вошло и чем всё
кончилось. Без истории администратор не сможет понять, был ли всплеск
случайным или чат обстреливают регулярно.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class RaidEvent(Base):
    """Зафиксированный налёт."""

    __tablename__ = "raid_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False
    )
    #: Сколько входов было замечено за окно наблюдения.
    joins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Что применялось к входящим, пока действовала тревога.
    action: Mapped[str] = mapped_column(String(16), nullable=False, default="captcha")
    #: Тревогу включил человек, а не бот.
    manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_raid_events_chat", "chat_id", "started_at"),)
