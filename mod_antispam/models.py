"""Данные антиспама (ТЗ §19).

Списки слов и разрешённых источников пересылок хранятся по чатам: то, что
в одном сообществе спам, в другом — обычный разговор.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class ForwardSource(StrEnum):
    """Откуда переслано сообщение."""

    USER = "user"
    CHAT = "chat"
    CHANNEL = "channel"
    HIDDEN = "hidden"  # отправитель скрыл себя: разрешить его нельзя


class ForbiddenWord(Base, TimestampMixin):
    """Запрещённое слово или выражение в конкретном чате."""

    __tablename__ = "forbidden_words"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False
    )
    #: Слово в нижнем регистре без лишних пробелов.
    word: Mapped[str] = mapped_column(String(128), nullable=False)
    added_by: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint("chat_id", "word", name="uq_forbidden_words_chat_word"),
        Index("ix_forbidden_words_chat", "chat_id"),
    )


class ForwardAllowance(Base, TimestampMixin):
    """Разрешённый источник пересылок.

    По умолчанию пересылки запрещены целиком, и список разрешает
    исключения: так новый спам-канал не пройдёт, пока его не разрешат.
    """

    __tablename__ = "forward_whitelist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Идентификатор пользователя или чата-источника.
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    added_by: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint(
            "chat_id", "source_type", "source_id", name="uq_forward_whitelist_source"
        ),
        Index("ix_forward_whitelist_chat", "chat_id"),
    )


class FilterState(Base, TimestampMixin):
    """Счётчик нарушений участника — для будущей эскалации.

    Хранится отдельно от предупреждений: нарушение фильтра не всегда
    должно становиться предупреждением, это решает настройка чата.
    """

    __tablename__ = "filter_violations"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule: Mapped[str] = mapped_column(String(32), primary_key=True)
    count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default=text("1")
    )
    notified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
