"""Приветствие новых участников (ТЗ §9)."""

from __future__ import annotations

from typing import Any

from aiogram.types import Message, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from mod_triggers.content import extract
from mod_triggers.models import ContentKind
from mod_triggers.repo import ContentRepository
from mod_welcome.models import WelcomeMessage
from sender.sender import Sender
from settings.service import SettingsService
from texts.entities import EntityText
from texts.placeholders import chat_values, user_values
from texts.service import TextService
from ui.buttons import ButtonSpec, build_inline

log = get_logger(__name__)


class WelcomeService:
    """Хранение и отправка приветствия."""

    def __init__(
        self,
        session: AsyncSession,
        settings: SettingsService,
        texts: TextService,
        sender: Sender,
    ) -> None:
        self._session = session
        self._settings = settings
        self._texts = texts
        self._sender = sender
        self._contents = ContentRepository(session)

    async def get(self, chat_id: int) -> WelcomeMessage | None:
        stmt = select(WelcomeMessage).where(WelcomeMessage.chat_id == chat_id)
        return (await self._session.execute(stmt)).unique().scalars().first()

    async def set_from_message(
        self, chat_id: int, source: Message, actor_id: int | None
    ) -> WelcomeMessage:
        """Сделать приветствием сообщение, на которое ответили.

        Прежнее приветствие удаляется вместе со своим содержимым, чтобы
        записи не накапливались.
        """
        fields = extract(source)
        content = await self._contents.create(**fields)

        existing = await self.get(chat_id)
        if existing is not None:
            old_content_id = existing.content_id
            existing.content = content
            existing.updated_by = actor_id
            await self._session.flush()
            await self._contents.delete(old_content_id)
            welcome = existing
        else:
            welcome = WelcomeMessage(chat_id=chat_id, content=content, updated_by=actor_id)
            self._session.add(welcome)
            await self._session.flush()

        log.info(
            "приветствие изменено",
            extra={"chat_id": chat_id, "kind": fields["kind"], "actor": actor_id},
        )
        return welcome

    async def clear(self, chat_id: int) -> bool:
        welcome = await self.get(chat_id)
        if welcome is None:
            return False

        content_id = welcome.content_id
        await self._session.delete(welcome)
        await self._session.flush()
        await self._contents.delete(content_id)
        return True

    async def send(self, chat_id: int, user: User, chat: Any) -> Message | None:
        """Поприветствовать участника.

        Если приветствие не настроено, используется текст по умолчанию из
        системы текстов — чат не остаётся вовсе без реакции на вход.
        """
        if not await self._settings.get(chat_id, "welcome.enabled"):
            return None

        welcome = await self.get(chat_id)
        values: dict[str, Any] = {}
        values.update(chat_values(chat))
        values.update(user_values(user))

        if welcome is None:
            body = await self._texts.render(chat_id, "welcome_default", values)
            sent = await self._sender.send(chat_id, body)
            return sent

        content = welcome.content
        body = EntityText.from_storage(content.text or "", content.entities).render(values)

        markup = None
        if content.keyboard:
            markup = build_inline(
                [[ButtonSpec.from_dict(button) for button in row] for row in content.keyboard]
            )

        if content.kind == ContentKind.TEXT:
            sent = await self._sender.send(chat_id, body, reply_markup=markup)
        else:
            sent = await self._sender.send_media(
                chat_id, content.kind, content.file_id, body, reply_markup=markup
            )

        # Прежнее приветствие убирается, иначе поток входов засоряет чат.
        if sent is not None:
            previous = welcome.last_message_id
            welcome.last_message_id = sent.message_id
            if previous and await self._settings.get(chat_id, "welcome.delete_previous"):
                await self._sender.delete_message(chat_id, previous)

        return sent
