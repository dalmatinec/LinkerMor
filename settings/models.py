"""Хранение настроек.

В базе лежат только переопределения: если чат не менял настройку, строки
для неё нет, и действует значение из реестра определений.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class ChatSetting(Base, TimestampMixin):
    """Переопределение настройки конкретным чатом.

    Ключ ``(chat_id, key)`` гарантирует изоляцию на уровне схемы: одна и та
    же настройка в разных чатах — это разные строки, и перепутать их нельзя.
    """

    __tablename__ = "chat_settings"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class SettingAudit(Base):
    """Журнал изменений настроек: кто, когда и что поменял."""

    __tablename__ = "settings_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[Any] = mapped_column(JSONB)
    new_value: Mapped[Any] = mapped_column(JSONB)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # История настроек чата показывается от свежих к старым.
        Index("ix_settings_audit_chat_created", "chat_id", "created_at"),
    )


class SystemSetting(Base, TimestampMixin):
    """Общесистемная настройка, доступная только владельцу бота."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
