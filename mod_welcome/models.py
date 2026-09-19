"""Приветствие чата.

Само сообщение хранится в общей таблице ``message_contents`` — той же, что
и ответы триггеров. Здесь только связь чата с его приветствием: так
приветствие сразу умеет всё, что умеет ответ триггера — вложение,
форматирование, премиум-эмодзи и кнопки.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin
from mod_triggers.models import MessageContent


class WelcomeMessage(Base, TimestampMixin):
    """Приветствие одного чата."""

    __tablename__ = "welcome_messages"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    content_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("message_contents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[MessageContent] = relationship(lazy="joined")
    updated_by: Mapped[int | None] = mapped_column(BigInteger)

    #: Идентификатор последнего отправленного приветствия: нужен, чтобы
    #: удалить предыдущее и не засорять чат при потоке входов.
    last_message_id: Mapped[int | None] = mapped_column(BigInteger)

    def __repr__(self) -> str:
        return f"<WelcomeMessage chat={self.chat_id}>"
