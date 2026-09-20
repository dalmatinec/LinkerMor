"""Центральная проверка прав (ТЗ §4, §26).

Право всегда определяется тройкой «пользователь + чат + действие».
Единственная глобальная проверка во всём проекте — принадлежность к
``OWNER_IDS``: владелец бота имеет доступ ко всем чатам. Для остальных
роль берётся из таблицы участников конкретного чата, поэтому один человек
может быть администратором в одном чате и рядовым участником в другом.

Проверяются не только права пользователя, но и права самого бота: если
Telegram не выдал боту нужное разрешение, команда обязана сообщить об этом
понятным текстом, а не падать с ошибкой API.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from core.constants import ANONYMOUS_ADMIN_BOT_ID, BotPermission, Role
from core.errors import BotMissingPermission, PermissionDenied
from core.logging import get_logger
from mod_chats.models import ChatMember
from mod_chats.repo import ChatRepository, MemberRepository

log = get_logger(__name__)

BOT_PERMS_CACHE_TTL = 300


class PermissionService:
    """Отвечает на вопросы о правах в конкретном чате."""

    def __init__(
        self,
        session: AsyncSession,
        cache: CacheBackend,
        owner_ids: frozenset[int],
        bot_id: int | None = None,
    ) -> None:
        self._session = session
        self._cache = cache
        self._owner_ids = owner_ids
        self._bot_id = bot_id
        self._members = MemberRepository(session)
        self._chats = ChatRepository(session)

    # ─── Роль пользователя ───────────────────────────────────────────────────

    async def role_of(
        self,
        chat_id: int,
        user_id: int,
        *,
        member: ChatMember | None = None,
        is_anonymous: bool = False,
    ) -> Role:
        """Роль пользователя в этом чате.

        Args:
            member: Уже загруженная запись участника. Передаётся из
                middleware, чтобы не читать базу повторно.
            is_anonymous: Сообщение пришло от анонимного администратора.

        Анонимному администратору Telegram не раскрывает личность: вместо
        человека приходит служебный бот. Писать анонимно может только
        администратор, поэтому такому отправителю выдаётся роль
        администратора чата — иначе владелец чата не смог бы пользоваться
        командами.
        """
        if user_id in self._owner_ids:
            return Role.BOT_OWNER

        if is_anonymous or user_id == ANONYMOUS_ADMIN_BOT_ID:
            return Role.CHAT_ADMIN

        record = member if member is not None else await self._members.get(chat_id, user_id)
        return Role(record.role) if record is not None else Role.MEMBER

    async def has_role(self, chat_id: int, user_id: int, minimum: Role, **kwargs) -> bool:
        return await self.role_of(chat_id, user_id, **kwargs) >= minimum

    async def require_role(
        self, chat_id: int, user_id: int, minimum: Role, **kwargs
    ) -> Role:
        """Убедиться, что роли достаточно.

        Raises:
            PermissionDenied: прав не хватает.
        """
        role = await self.role_of(chat_id, user_id, **kwargs)
        if role < minimum:
            log.info(
                "отказано в доступе",
                extra={"chat_id": chat_id, "actor": user_id, "role": role.name,
                       "required": minimum.name},
            )
            raise PermissionDenied(
                "Недостаточно прав", chat_id=chat_id, user_id=user_id, required=minimum.name
            )
        return role

    # ─── Права бота ──────────────────────────────────────────────────────────

    async def bot_permissions(self, chat_id: int) -> dict[str, bool]:
        """Права бота в чате, как их выдал Telegram."""
        key = chat_key(ChatEntity.BOT_PERMS, chat_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        chat = await self._chats.get(chat_id)
        permissions = dict(chat.bot_permissions) if chat is not None else {}
        await self._cache.set(key, permissions, ttl=BOT_PERMS_CACHE_TTL)
        return permissions

    async def bot_can(self, chat_id: int, permission: BotPermission | str) -> bool:
        name = permission.value if isinstance(permission, BotPermission) else permission
        return bool((await self.bot_permissions(chat_id)).get(name, False))

    async def require_bot_permission(self, chat_id: int, permission: BotPermission | str) -> None:
        """Убедиться, что у бота есть право Telegram.

        Raises:
            BotMissingPermission: права нет — пользователь получит текст
                с названием недостающего разрешения.
        """
        name = permission.value if isinstance(permission, BotPermission) else permission
        if not await self.bot_can(chat_id, name):
            log.info("боту не хватает права", extra={"chat_id": chat_id, "permission": name})
            raise BotMissingPermission(name, chat_id=chat_id)

    async def invalidate_bot_permissions(self, chat_id: int) -> None:
        """Сбросить кеш прав бота после их изменения."""
        await self._cache.delete(chat_key(ChatEntity.BOT_PERMS, chat_id))

    # ─── Модерация ───────────────────────────────────────────────────────────

    async def can_act_on(self, chat_id: int, actor_id: int, target_id: int) -> bool:
        """Может ли администратор применить меру к этому пользователю.

        Модератор не должен наказывать равного себе или старшего: иначе
        два администратора способны заблокировать друг друга.
        """
        if target_id == self._bot_id:
            return False
        if actor_id == target_id:
            return False

        actor_role = await self.role_of(chat_id, actor_id)
        target_role = await self.role_of(chat_id, target_id)
        return actor_role > target_role

    async def require_can_act_on(self, chat_id: int, actor_id: int, target_id: int) -> None:
        """Raises: PermissionDenied — цель защищена от этого администратора."""
        if not await self.can_act_on(chat_id, actor_id, target_id):
            raise PermissionDenied(
                "Нельзя применить меру к этому пользователю",
                chat_id=chat_id,
                user_id=actor_id,
                target_id=target_id,
            )

    async def is_owner(self, user_id: int) -> bool:
        """Владелец бота: единственная глобальная роль."""
        return user_id in self._owner_ids
