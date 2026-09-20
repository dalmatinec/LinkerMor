"""Базовый класс моделей и общие примеси.

Соглашение об именах ограничений задано явно: без него Alembic даёт
безымянные constraint'ы, которые потом невозможно изменить миграцией.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Детерминированные имена ограничений и индексов для Alembic.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Общий предок всех моделей проекта."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Отметки создания и изменения. Время ставит база, не приложение."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ChatScopedMixin:
    """Привязка строки к чату — фундамент изоляции данных (ТЗ §22).

    Каждая таблица с данными конкретного чата наследует эту примесь, и
    ``chat_id`` входит в её первичный или уникальный ключ. Изоляция
    обеспечивается схемой, а не аккуратностью разработчика.
    """

    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


def import_all_models() -> None:
    """Импортировать модели, не принадлежащие ни одному модулю.

    Модели модулей попадают в метаданные через их ``spec``. Настройки и
    тексты — часть ядра, поэтому импортируются здесь.
    """
    import settings.models  # noqa: F401
    import texts.models  # noqa: F401
