"""Определение цели команды модерации (ТЗ §7).

Команды принимают цель тремя способами: ответом на сообщение, упоминанием
и числовым идентификатором. Логика разбора собрана здесь, чтобы каждая
команда не изобретала свою.

Главное ограничение Bot API: метода «@username → user_id» не существует.
Поэтому по username находятся только те, кого бот уже видел — их данные
попадают в справочник из каждого обработанного апдейта. Для остальных
выдаётся понятное объяснение, а не молчание.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import TargetNotFound
from core.logging import get_logger
from mod_chats.repo import UserRepository

log = get_logger(__name__)


class TargetSource(StrEnum):
    """Как была определена цель — попадает в журнал действий."""

    REPLY = "reply"
    MENTION = "mention"  # упоминание без username, Telegram прислал профиль
    USERNAME = "username"
    USER_ID = "user_id"
    SENDER_CHAT = "sender_chat"  # сообщение от имени канала


@dataclass(frozen=True, slots=True)
class Target:
    """Цель команды модерации."""

    id: int
    display_name: str
    source: TargetSource
    username: str | None = None
    #: Сообщение отправлено от имени канала: нужен banChatSenderChat.
    is_chat: bool = False

    @property
    def mention_name(self) -> str:
        return f"@{self.username}" if self.username else self.display_name


def split_argument(text: str | None) -> tuple[str | None, str]:
    """Разделить аргументы команды на цель и остаток.

    ``@user спам и флуд`` → ``("@user", "спам и флуд")``.
    Остаток используется как причина наказания.
    """
    if not text or not text.strip():
        return None, ""
    parts = text.strip().split(maxsplit=1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


class UserResolver:
    """Находит пользователя, к которому относится команда."""

    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)

    async def resolve(self, message: Message, argument: str | None = None) -> Target:
        """Определить цель команды.

        Ответ на сообщение имеет приоритет над аргументом: так администратор
        может ответить на сообщение нарушителя и сразу написать причину.

        Raises:
            TargetNotFound: цель не указана или не найдена.
        """
        target = self._from_reply(message)
        if target is not None:
            return target

        target = self._from_entities(message)
        if target is not None:
            return target

        if argument:
            return await self.resolve_token(argument)

        raise TargetNotFound("Цель команды не указана")

    async def resolve_token(self, token: str) -> Target:
        """Определить цель по одному аргументу: ``@username`` или ID."""
        token = token.strip()

        if token.lstrip("-").isdigit():
            user_id = int(token)
            stored = await self._users.get(user_id)
            return Target(
                id=user_id,
                display_name=stored.full_name if stored else str(user_id),
                source=TargetSource.USER_ID,
                username=stored.username if stored else None,
            )

        if token.startswith("@") or token.isascii():
            stored = await self._users.find_by_username(token)
            if stored is None:
                log.info("пользователь не найден по username", extra={"token": token})
                raise TargetNotFound("Пользователь не найден по username", token=token)
            return Target(
                id=stored.user_id,
                display_name=stored.full_name,
                source=TargetSource.USERNAME,
                username=stored.username,
            )

        raise TargetNotFound("Не удалось разобрать цель команды", token=token)

    @staticmethod
    def _from_reply(message: Message) -> Target | None:
        """Цель из сообщения, на которое ответили."""
        reply = message.reply_to_message
        if reply is None:
            return None

        # Сообщение от имени канала: банить придётся канал, а не человека.
        if reply.sender_chat is not None:
            return Target(
                id=reply.sender_chat.id,
                display_name=reply.sender_chat.title or str(reply.sender_chat.id),
                source=TargetSource.SENDER_CHAT,
                username=reply.sender_chat.username,
                is_chat=True,
            )

        user = reply.from_user
        if user is None:
            return None
        name = " ".join(filter(None, (user.first_name, user.last_name))) or str(user.id)
        return Target(
            id=user.id,
            display_name=name,
            source=TargetSource.REPLY,
            username=user.username,
        )

    @staticmethod
    def _from_entities(message: Message) -> Target | None:
        """Цель из упоминания пользователя без username.

        Telegram присылает для таких упоминаний готовый профиль в entity
        ``text_mention`` — это единственный способ сослаться на человека,
        у которого username нет.
        """
        for entity in message.entities or []:
            if entity.type == "text_mention" and entity.user is not None:
                user = entity.user
                name = " ".join(filter(None, (user.first_name, user.last_name))) or str(user.id)
                return Target(
                    id=user.id,
                    display_name=name,
                    source=TargetSource.MENTION,
                    username=user.username,
                )
        return None
