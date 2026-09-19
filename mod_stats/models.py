"""Ежедневная активность участников.

Счётчик за всё время уже есть в ``chat_members``, но по нему нельзя
ответить на вопрос «сколько писали на этой неделе». Поэтому активность
дополнительно копится по дням.

Строка на пару «участник + день» — это компромисс: точнее, чем общий
счётчик чата, и во много раз дешевле, чем хранение самих сообщений,
которые бот не сохраняет принципиально.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class DailyActivity(Base):
    """Сколько сообщений написал участник в конкретный день."""

    __tablename__ = "activity_daily"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    messages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        # Сводка чата за период: выборка по дням.
        Index("ix_activity_chat_day", "chat_id", "day"),
    )
