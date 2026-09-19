"""Модели чатов, пользователей и участников.

Три таблицы образуют основу мультичатовой изоляции: всё остальное в проекте
ссылается на ``chats.chat_id`` и ``users.user_id``, а роли и статистика
живут в ``chat_members`` — по строке на пару «чат + пользователь».
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import ChatStatus, Role
from database.base import Base, TimestampMixin


class Chat(Base, TimestampMixin):
    """Подключённый чат.

    Строка создаётся при добавлении бота в чат и больше не удаляется:
    настройки и накопленные данные переживают исключение бота.
    """

    __tablename__ = "chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ChatStatus.ACTIVE, server_default=ChatStatus.ACTIVE
    )
    #: Статус самого бота в чате: administrator, member, left, kicked.
    bot_status: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    #: Права бота, как их прислал Telegram. Проверяются перед каждым действием.
    bot_permissions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    added_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Куда переехал чат после превращения группы в супергруппу.
    migrated_to_chat_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        # Списки чатов в панели владельца фильтруются по состоянию.
        Index("ix_chats_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Chat {self.chat_id} {self.title!r} {self.status}>"


class User(Base, TimestampMixin):
    """Пользователь, которого бот видел хотя бы раз.

    Таблица одновременно служит справочником для резолва ``@username``:
    в Bot API нет метода, превращающего username в ``user_id``, поэтому
    единственный надёжный источник — те, кого бот уже встречал.
    """

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language_code: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        # Резолв идёт без учёта регистра: @Durov и @durov — один человек.
        Index("ix_users_username_lower", func.lower(username), postgresql_where=username.isnot(None)),
    )

    @property
    def full_name(self) -> str:
        return " ".join(filter(None, (self.first_name, self.last_name))) or str(self.user_id)

    def __repr__(self) -> str:
        return f"<User {self.user_id} @{self.username}>"


class ChatMember(Base, TimestampMixin):
    """Участник конкретного чата: роль, права и накопленная статистика.

    Ключ ``(chat_id, user_id)`` — причина, по которой один человек может
    быть администратором в одном чате и рядовым участником в другом.
    """

    __tablename__ = "chat_members"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )

    #: Роль уровня бота: значение перечисления Role.
    role: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=Role.MEMBER, server_default=str(int(Role.MEMBER))
    )
    #: Статус в Telegram: creator, administrator, member, restricted, left, kicked.
    tg_status: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    #: Права администратора, как их прислал Telegram.
    tg_permissions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: Администратор скрыл себя за подписью группы.
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Счётчик сообщений: метрика рангов, настраиваемая для каждого чата.
    #: Инкремент атомарный, поэтому пересчёт агрегатом не нужен.
    messages_total: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )

    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # «Мои чаты» в админ-панели: выборка по пользователю.
        Index("ix_chat_members_user_id", "user_id"),
        # Список администраторов чата: частичный индекс вместо полного.
        Index(
            "ix_chat_members_staff",
            "chat_id",
            "role",
            postgresql_where=text(f"role > {int(Role.MEMBER)}"),
        ),
        # Топ активных участников чата.
        Index("ix_chat_members_activity", "chat_id", text("messages_total DESC")),
    )

    @property
    def is_staff(self) -> bool:
        """Модератор, администратор или создатель чата."""
        return self.role > Role.MEMBER

    def __repr__(self) -> str:
        return f"<ChatMember chat={self.chat_id} user={self.user_id} role={self.role}>"
