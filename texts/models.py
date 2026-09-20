"""Хранение настраиваемых текстов (ТЗ §13).

Два уровня переопределения: глобальный, доступный владельцу бота, и
уровень конкретного чата. Значения по умолчанию лежат в реестре кода,
поэтому таблицы содержат только то, что кто-то действительно изменил.

Колонка ``lang`` заложена заранее: сейчас используется только русский, но
добавление языка не потребует миграции.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import DEFAULT_LANGUAGE
from database.base import Base, TimestampMixin


class GlobalText(Base, TimestampMixin):
    """Текст, изменённый владельцем бота для всех чатов сразу."""

    __tablename__ = "global_texts"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    lang: Mapped[str] = mapped_column(
        String(8), primary_key=True, default=DEFAULT_LANGUAGE, server_default=DEFAULT_LANGUAGE
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Форматирование: жирный, ссылки, премиум-эмодзи.
    entities: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class ChatText(Base, TimestampMixin):
    """Текст, изменённый администратором конкретного чата.

    Ключ ``(chat_id, key, lang)`` — изоляция на уровне схемы: текст чата A
    физически не может быть прочитан как текст чата B.
    """

    __tablename__ = "chat_texts"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    lang: Mapped[str] = mapped_column(
        String(8), primary_key=True, default=DEFAULT_LANGUAGE, server_default=DEFAULT_LANGUAGE
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
