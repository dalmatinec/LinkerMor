"""Сессии проверки при входе.

Состояние хранится в базе, а не в памяти: проверка длится минуты, и
перезапуск бота не должен оставлять человека в муте навсегда.

Ключ ``(chat_id, user_id)`` одновременно служит защитой от гонки: при
нескольких событиях входа подряд вставка второй сессии просто не
произойдёт.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class CaptchaKind(StrEnum):
    """Вид проверки."""

    BUTTON = "button"  # одна кнопка: отсекает простейшие автоматические входы
    MATH = "math"  # простой пример с выбором ответа
    EMOJI = "emoji"  # выбрать названный символ


class CaptchaSession(Base, TimestampMixin):
    """Идущая проверка одного человека в одном чате."""

    __tablename__ = "captcha_sessions"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    answer: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts_left: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Сообщение с проверкой: удаляется после прохождения или провала.
    message_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        # Фоновая задача ищет просроченные проверки по сроку.
        Index("ix_captcha_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<CaptchaSession chat={self.chat_id} user={self.user_id}>"
