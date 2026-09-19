"""Жизненный цикл чата: подключение, потеря прав, отключение, переезд (ТЗ §5).

Событие ``my_chat_member`` приходит при каждом изменении положения бота в
чате. Оно же служит единственным надёжным признаком подключения: полагаться
на первое сообщение нельзя, потому что бот может быть добавлен в молчащий чат.
"""

from __future__ import annotations

from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import ChatStatus, Role
from core.logging import get_logger
from mod_chats.models import Chat
from mod_chats.repo import ChatRepository, MemberRepository, UserRepository

log = get_logger(__name__)

#: Статусы, при которых бот способен работать в чате.
ACTIVE_BOT_STATUSES = frozenset({"administrator", "member"})

#: Права администратора, которые Telegram присылает в ChatMemberAdministrator.
TRACKED_PERMISSIONS = (
    "can_delete_messages",
    "can_restrict_members",
    "can_invite_users",
    "can_pin_messages",
    "can_manage_chat",
    "can_promote_members",
    "can_change_info",
    "can_manage_video_chats",
    "can_manage_topics",
    "can_send_welcome_messages",  # Bot API 10.3: нужно welcome-модулю
)


def extract_permissions(member) -> dict[str, bool]:  # noqa: ANN001 - тип из aiogram
    """Собрать словарь прав из объекта участника.

    Обычный участник прав администратора не имеет, поэтому для него
    возвращается пустой словарь — так проверки прав работают единообразно.
    """
    return {
        name: bool(getattr(member, name, False))
        for name in TRACKED_PERMISSIONS
        if getattr(member, name, None) is not None
    }


def role_from_status(status: str) -> Role:
    """Сопоставить статус Telegram с ролью бота."""
    if status == "creator":
        return Role.CHAT_OWNER
    if status == "administrator":
        return Role.CHAT_ADMIN
    return Role.MEMBER


class ChatLifecycleService:
    """Подключение и отключение чатов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._chats = ChatRepository(session)
        self._users = UserRepository(session)
        self._members = MemberRepository(session)

    async def handle_bot_update(self, event: ChatMemberUpdated) -> Chat | None:
        """Обработать изменение положения бота в чате.

        Returns:
            Запись чата, если бот в нём работает, иначе ``None``.
        """
        new_status = event.new_chat_member.status
        chat = event.chat

        if new_status in ACTIVE_BOT_STATUSES:
            return await self._connect(event)

        # left или kicked: чат деактивируется, данные сохраняются.
        await self._chats.set_status(chat.id, ChatStatus.INACTIVE, new_status)
        log.info(
            "бот удалён из чата",
            extra={"chat_id": chat.id, "bot_status": new_status, "actor": event.from_user.id},
        )
        return None

    async def _connect(self, event: ChatMemberUpdated) -> Chat:
        """Создать или оживить чат и завести того, кто добавил бота."""
        actor = event.from_user
        await self._users.upsert(
            user_id=actor.id,
            username=actor.username,
            first_name=actor.first_name,
            last_name=actor.last_name,
            is_bot=actor.is_bot,
            language_code=actor.language_code,
        )

        permissions = extract_permissions(event.new_chat_member)
        chat = await self._chats.upsert(
            chat_id=event.chat.id,
            type_=event.chat.type,
            title=event.chat.title,
            username=event.chat.username,
            bot_status=event.new_chat_member.status,
            bot_permissions=permissions,
            added_by_user_id=actor.id,
        )

        # Тот, кто добавил бота, почти всегда администратор чата.
        await self._members.upsert(
            chat_id=chat.chat_id,
            user_id=actor.id,
            role=Role.CHAT_ADMIN,
            tg_status="administrator",
        )

        was_reconnect = event.old_chat_member.status not in ACTIVE_BOT_STATUSES
        log.info(
            "чат подключён" if was_reconnect else "права бота обновлены",
            extra={
                "chat_id": chat.chat_id,
                "title": chat.title,
                "bot_status": chat.bot_status,
                "granted": sorted(k for k, v in permissions.items() if v),
            },
        )
        return chat

    async def handle_migration(self, old_chat_id: int, new_chat_id: int, chat) -> Chat:  # noqa: ANN001
        """Перенести данные после превращения группы в супергруппу.

        Telegram выдаёт супергруппе новый ``chat_id``. Без переноса чат
        выглядел бы как новый и потерял бы все настройки и статистику.
        """
        new_chat = await self._chats.upsert(
            chat_id=new_chat_id,
            type_="supergroup",
            title=chat.title,
            username=getattr(chat, "username", None),
            bot_status="administrator",
            bot_permissions={},
        )
        moved = await self._members.move_to_chat(old_chat_id, new_chat_id)
        await self._chats.mark_migrated(old_chat_id, new_chat_id)

        log.warning(
            "чат переехал в супергруппу",
            extra={"chat_id": old_chat_id, "new_chat_id": new_chat_id, "members_moved": moved},
        )
        return new_chat

    async def handle_member_update(self, event: ChatMemberUpdated) -> None:
        """Обновить роль участника после изменения его статуса в чате."""
        user = event.new_chat_member.user
        await self._users.upsert(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            is_bot=user.is_bot,
            language_code=user.language_code,
        )

        status = event.new_chat_member.status
        await self._members.upsert(
            chat_id=event.chat.id,
            user_id=user.id,
            role=role_from_status(status),
            tg_status=status,
            tg_permissions=extract_permissions(event.new_chat_member),
            is_anonymous=bool(getattr(event.new_chat_member, "is_anonymous", False)),
        )
        log.debug(
            "статус участника обновлён",
            extra={"chat_id": event.chat.id, "target_id": user.id, "status": status},
        )
