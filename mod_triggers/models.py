"""Триггеры и хранилище сообщений-ответов.

``MessageContent`` — отдельная таблица, а не поля внутри триггера. Тот же
формат понадобится приветствию, капче и рассылкам: везде нужно сохранить
сообщение администратора со всем оформлением и воспроизвести его позже.

Сохраняется не «текст», а полный набор: тип вложения, идентификатор файла,
подпись, entity и клавиатура. Иначе премиум-эмодзи и форматирование
пропадут при первой же отправке.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text  # колонка «text» перекрывает имя функции
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin


class ContentKind(StrEnum):
    """Что представляет собой сохранённое сообщение."""

    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    ANIMATION = "animation"
    DOCUMENT = "document"
    AUDIO = "audio"
    VOICE = "voice"
    VIDEO_NOTE = "video_note"
    STICKER = "sticker"


class MatchType(StrEnum):
    """Как ключевое слово сравнивается с сообщением."""

    WORD = "word"  # отдельным словом: «привет» не сработает в «приветствие»
    EXACT = "exact"  # сообщение целиком равно ключу
    CONTAINS = "contains"  # ключ встречается где угодно, в том числе внутри слова
    REGEX = "regex"  # регулярное выражение, доступно только владельцу бота


class MessageContent(Base, TimestampMixin):
    """Сохранённое сообщение вместе с оформлением."""

    __tablename__ = "message_contents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ContentKind.TEXT)

    #: Текст сообщения или подпись к вложению.
    text: Mapped[str | None] = mapped_column(Text)
    #: Форматирование текста: жирный, ссылки, премиум-эмодзи.
    entities: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )

    #: Идентификатор вложения в Telegram. Привязан к боту, поэтому
    #: пересоздание бота потребует загрузить файлы заново.
    file_id: Mapped[str | None] = mapped_column(String(256))
    file_unique_id: Mapped[str | None] = mapped_column(String(128))

    #: Клавиатура в формате ButtonSpec: текст, стиль, премиум-эмодзи, действие.
    keyboard: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )

    def __repr__(self) -> str:
        return f"<MessageContent {self.id} {self.kind}>"


class Trigger(Base, TimestampMixin):
    """Ключевое слово и ответ на него в конкретном чате."""

    __tablename__ = "triggers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False
    )

    #: Ключ в нормализованном виде: нижний регистр, без лишних пробелов.
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Ключ в том виде, в каком его ввёл администратор — для показа в списке.
    display_key: Mapped[str] = mapped_column(String(128), nullable=False)
    match_type: Mapped[str] = mapped_column(String(16), nullable=False, default=MatchType.WORD)

    content_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("message_contents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[MessageContent] = relationship(lazy="joined")

    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )
    #: Не отвечать чаще, чем раз в столько секунд. Защита от превращения
    #: триггера в инструмент флуда.
    cooldown: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    hits: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=sql_text("0")
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        # Одно ключевое слово — один триггер в пределах чата.
        UniqueConstraint("chat_id", "key", name="uq_triggers_chat_key"),
        # Загрузка всех действующих триггеров чата одним запросом.
        Index("ix_triggers_enabled", "chat_id", postgresql_where=sql_text("is_enabled")),
    )

    def __repr__(self) -> str:
        return f"<Trigger {self.chat_id}:{self.key}>"
