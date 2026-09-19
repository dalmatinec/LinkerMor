"""Обращения к Telegram для мер модерации.

Отделено от бизнес-логики: сервис решает, что делать, а этот слой знает,
каким методом API это выполняется и какие отказы ожидаемы.
"""

from __future__ import annotations

from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import ChatPermissions

from core.logging import get_logger

log = get_logger(__name__)

#: Полное ограничение: участник остаётся в чате, но не может писать.
MUTED = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)


class ModerationActions:
    """Выполняет меры модерации через Bot API."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def ban(
        self,
        chat_id: int,
        target_id: int,
        *,
        until: datetime | None = None,
        is_chat: bool = False,
    ) -> bool:
        """Заблокировать участника или канал-отправитель.

        Сообщения от имени канала снимаются отдельным методом: обычный бан
        на такого отправителя не действует.
        """
        try:
            if is_chat:
                await self._bot.ban_chat_sender_chat(chat_id=chat_id, sender_chat_id=target_id)
            else:
                await self._bot.ban_chat_member(
                    chat_id=chat_id, user_id=target_id, until_date=until
                )
            return True
        except TelegramAPIError as exc:
            log.warning(
                "не удалось заблокировать",
                extra={"chat_id": chat_id, "target_id": target_id, "reason": str(exc)},
            )
            return False

    async def unban(self, chat_id: int, target_id: int, *, is_chat: bool = False) -> bool:
        try:
            if is_chat:
                await self._bot.unban_chat_sender_chat(chat_id=chat_id, sender_chat_id=target_id)
            else:
                # only_if_banned: иначе Telegram трактует вызов как
                # приглашение и выкидывает участника из чата.
                await self._bot.unban_chat_member(
                    chat_id=chat_id, user_id=target_id, only_if_banned=True
                )
            return True
        except TelegramAPIError as exc:
            log.warning(
                "не удалось разблокировать",
                extra={"chat_id": chat_id, "target_id": target_id, "reason": str(exc)},
            )
            return False

    async def mute(self, chat_id: int, user_id: int, until: datetime | None = None) -> bool:
        try:
            await self._bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id, permissions=MUTED, until_date=until
            )
            return True
        except TelegramAPIError as exc:
            log.warning(
                "не удалось ограничить",
                extra={"chat_id": chat_id, "target_id": user_id, "reason": str(exc)},
            )
            return False

    async def unmute(self, chat_id: int, user_id: int) -> bool:
        """Снять ограничение, вернув права, принятые в этом чате.

        Выдавать все права подряд нельзя: в чате могут быть запрещены,
        например, опросы, и снятие мута не должно это отменять.
        """
        permissions = await self._chat_permissions(chat_id)
        try:
            await self._bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id, permissions=permissions, until_date=None
            )
            return True
        except TelegramAPIError as exc:
            log.warning(
                "не удалось снять ограничение",
                extra={"chat_id": chat_id, "target_id": user_id, "reason": str(exc)},
            )
            return False

    async def kick(self, chat_id: int, user_id: int) -> bool:
        """Удалить из чата с правом вернуться: бан и немедленное снятие."""
        if not await self.ban(chat_id, user_id):
            return False
        return await self.unban(chat_id, user_id)

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        try:
            await self._bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except TelegramBadRequest:
            # Сообщение уже удалено — это не ошибка.
            return False
        except TelegramAPIError:
            return False

    async def _chat_permissions(self, chat_id: int) -> ChatPermissions:
        """Права участников по умолчанию в этом чате."""
        try:
            chat = await self._bot.get_chat(chat_id)
        except TelegramAPIError:
            chat = None

        if chat is not None and chat.permissions is not None:
            return chat.permissions

        # Чат не отдал настройки: возвращаем базовый набор для общения.
        return ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_invite_users=True,
        )
