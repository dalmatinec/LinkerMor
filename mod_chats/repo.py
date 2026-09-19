"""Доступ к данным чатов, пользователей и участников.

Весь SQL модуля живёт здесь: хендлеры и сервисы работают только через эти
методы. Записи выполняются через ``INSERT ... ON CONFLICT``, поэтому
одновременная обработка нескольких апдейтов одного пользователя не создаёт
дублей и не требует блокировок.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import ChatStatus, Role
from mod_chats.models import Chat, ChatMember, User


class ChatRepository:
    """Операции над таблицей чатов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, chat_id: int) -> Chat | None:
        return await self._session.get(Chat, chat_id)

    async def upsert(
        self,
        *,
        chat_id: int,
        type_: str,
        title: str | None,
        username: str | None,
        bot_status: str,
        bot_permissions: dict,
        added_by_user_id: int | None = None,
    ) -> Chat:
        """Создать чат или обновить его данные, сохранив прежние настройки.

        ``connected_at`` и ``added_by_user_id`` пишутся только при первом
        подключении: при возвращении бота история подключения не теряется.
        """
        stmt = (
            insert(Chat)
            .values(
                chat_id=chat_id,
                type=type_,
                title=title,
                username=username,
                status=ChatStatus.ACTIVE,
                bot_status=bot_status,
                bot_permissions=bot_permissions,
                added_by_user_id=added_by_user_id,
                last_seen_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=[Chat.chat_id],
                set_={
                    "type": type_,
                    "title": title,
                    "username": username,
                    "status": ChatStatus.ACTIVE,
                    "bot_status": bot_status,
                    "bot_permissions": bot_permissions,
                    "last_seen_at": datetime.now(UTC),
                    "updated_at": func.now(),
                },
            )
            .returning(Chat)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def set_status(self, chat_id: int, status: ChatStatus, bot_status: str) -> None:
        """Перевести чат в другое состояние, не трогая его настройки."""
        await self._session.execute(
            update(Chat)
            .where(Chat.chat_id == chat_id)
            .values(status=status, bot_status=bot_status, updated_at=func.now())
        )

    async def mark_migrated(self, old_chat_id: int, new_chat_id: int) -> None:
        """Отметить переезд группы в супергруппу."""
        await self._session.execute(
            update(Chat)
            .where(Chat.chat_id == old_chat_id)
            .values(
                status=ChatStatus.MIGRATED,
                migrated_to_chat_id=new_chat_id,
                updated_at=func.now(),
            )
        )

    async def update_bot_permissions(self, chat_id: int, permissions: dict, bot_status: str) -> None:
        await self._session.execute(
            update(Chat)
            .where(Chat.chat_id == chat_id)
            .values(bot_permissions=permissions, bot_status=bot_status, updated_at=func.now())
        )

    async def list_by_status(self, status: ChatStatus, limit: int = 50, offset: int = 0) -> list[Chat]:
        """Страница чатов для панели владельца."""
        stmt = (
            select(Chat)
            .where(Chat.status == status)
            .order_by(Chat.connected_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(Chat.status, func.count()).group_by(Chat.status)
        return {status: count for status, count in (await self._session.execute(stmt)).all()}


class UserRepository:
    """Справочник пользователей и резолв username."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def upsert(
        self,
        *,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        is_bot: bool = False,
        is_premium: bool = False,
        language_code: str | None = None,
    ) -> User:
        """Записать или освежить данные пользователя.

        Вызывается для каждого апдейта, поэтому username в справочнике
        всегда соответствует последнему увиденному.
        """
        stmt = (
            insert(User)
            .values(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_bot=is_bot,
                is_premium=is_premium,
                language_code=language_code,
            )
            .on_conflict_do_update(
                index_elements=[User.user_id],
                set_={
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_premium": is_premium,
                    "language_code": language_code,
                    "updated_at": func.now(),
                },
            )
            .returning(User)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def find_by_username(self, username: str) -> User | None:
        """Найти пользователя по username без учёта регистра.

        Работает только для тех, кого бот уже видел: метода «username →
        user_id» в Bot API не существует.
        """
        normalized = username.lstrip("@").lower()
        stmt = select(User).where(func.lower(User.username) == normalized)
        return (await self._session.execute(stmt)).scalars().first()


class MemberRepository:
    """Роли и статистика участников в разрезе чата."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, chat_id: int, user_id: int) -> ChatMember | None:
        return await self._session.get(ChatMember, (chat_id, user_id))

    async def upsert(
        self,
        *,
        chat_id: int,
        user_id: int,
        role: Role,
        tg_status: str,
        tg_permissions: dict | None = None,
        is_anonymous: bool = False,
    ) -> ChatMember:
        stmt = (
            insert(ChatMember)
            .values(
                chat_id=chat_id,
                user_id=user_id,
                role=int(role),
                tg_status=tg_status,
                tg_permissions=tg_permissions or {},
                is_anonymous=is_anonymous,
                joined_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=[ChatMember.chat_id, ChatMember.user_id],
                set_={
                    "role": int(role),
                    "tg_status": tg_status,
                    "tg_permissions": tg_permissions or {},
                    "is_anonymous": is_anonymous,
                    "updated_at": func.now(),
                },
            )
            .returning(ChatMember)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def ensure_exists(self, chat_id: int, user_id: int) -> None:
        """Завести участника, не трогая роль, если запись уже есть."""
        stmt = (
            insert(ChatMember)
            .values(chat_id=chat_id, user_id=user_id, role=int(Role.MEMBER), tg_status="member")
            .on_conflict_do_nothing(index_elements=[ChatMember.chat_id, ChatMember.user_id])
        )
        await self._session.execute(stmt)

    async def list_staff(self, chat_id: int) -> list[ChatMember]:
        """Модераторы, администраторы и создатель чата."""
        stmt = (
            select(ChatMember)
            .where(ChatMember.chat_id == chat_id, ChatMember.role > int(Role.MEMBER))
            .order_by(ChatMember.role.desc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_chats_for_user(self, user_id: int, min_role: Role = Role.MODERATOR) -> list[Chat]:
        """Чаты, администрирование которых доступно пользователю.

        Источник данных для выбора чата в админ-панели: пользователь видит
        только те чаты, где у него есть права.
        """
        stmt = (
            select(Chat)
            .join(ChatMember, ChatMember.chat_id == Chat.chat_id)
            .where(
                ChatMember.user_id == user_id,
                ChatMember.role >= int(min_role),
                Chat.status == ChatStatus.ACTIVE,
            )
            .order_by(Chat.title)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def demote_missing_admins(self, chat_id: int, keep_user_ids: set[int]) -> int:
        """Снять роль с тех, кого больше нет в списке администраторов чата.

        Вызывается после синхронизации: Telegram не присылает событие о
        снятии прав, если бот в это время был офлайн.
        """
        stmt = (
            update(ChatMember)
            .where(
                ChatMember.chat_id == chat_id,
                ChatMember.role >= int(Role.CHAT_ADMIN),
                ChatMember.user_id.notin_(keep_user_ids or {0}),
            )
            .values(role=int(Role.MEMBER), tg_permissions={}, updated_at=func.now())
        )
        return (await self._session.execute(stmt)).rowcount

    async def increment_messages(self, chat_id: int, user_id: int) -> int:
        """Атомарно увеличить счётчик сообщений и вернуть новое значение.

        Инкремент выполняется одним запросом без чтения предыдущего
        значения, поэтому параллельные сообщения не теряются.
        """
        stmt = (
            update(ChatMember)
            .where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
            .values(
                messages_total=ChatMember.messages_total + 1,
                last_message_at=datetime.now(UTC),
            )
            .returning(ChatMember.messages_total)
        )
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        return result or 0

    async def move_to_chat(self, old_chat_id: int, new_chat_id: int) -> int:
        """Перенести участников при переезде группы в супергруппу."""
        stmt = (
            update(ChatMember)
            .where(ChatMember.chat_id == old_chat_id)
            .values(chat_id=new_chat_id)
        )
        return (await self._session.execute(stmt)).rowcount
