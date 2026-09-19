"""Синхронизация администраторов чата (ТЗ §5).

Событий ``chat_member`` недостаточно: пока бот был офлайн, права могли
измениться без его ведома. Поэтому список администраторов периодически
сверяется с Telegram напрямую.

Вызов ``getChatAdministrators`` ограничен по частоте, поэтому результат
кешируется, а сам список хранится в базе и переживает перезапуск.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from core.constants import Role
from core.logging import get_logger
from mod_chats.lifecycle import extract_permissions, role_from_status
from mod_chats.repo import MemberRepository, UserRepository

log = get_logger(__name__)

#: Насколько часто допустимо ходить в Telegram за списком администраторов.
ADMIN_CACHE_TTL = 600


class AdminSyncService:
    """Приводит роли в базе в соответствие с реальными правами в Telegram."""

    def __init__(self, session: AsyncSession, bot: Bot, cache: CacheBackend) -> None:
        self._session = session
        self._bot = bot
        self._cache = cache
        self._users = UserRepository(session)
        self._members = MemberRepository(session)

    async def sync(self, chat_id: int, *, force: bool = False) -> int:
        """Сверить администраторов чата с Telegram.

        Args:
            chat_id: Чат для синхронизации.
            force: Игнорировать кеш и обратиться к Telegram немедленно.

        Returns:
            Количество найденных администраторов. ``0`` — если данные взяты
            из кеша или Telegram отказал в запросе.
        """
        key = chat_key(ChatEntity.ADMINS, chat_id)
        if not force and await self._cache.get(key) is not None:
            return 0

        try:
            administrators = await self._bot.get_chat_administrators(chat_id)
        except TelegramAPIError as exc:
            # Бота могли исключить между событиями: это не повод падать.
            log.warning(
                "не удалось получить администраторов",
                extra={"chat_id": chat_id, "reason": str(exc)},
            )
            return 0

        seen: set[int] = set()
        for member in administrators:
            user = member.user
            if user.is_bot:
                continue

            await self._users.upsert(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_bot=user.is_bot,
                language_code=user.language_code,
            )
            await self._members.upsert(
                chat_id=chat_id,
                user_id=user.id,
                role=role_from_status(member.status),
                tg_status=member.status,
                tg_permissions=extract_permissions(member),
                is_anonymous=bool(getattr(member, "is_anonymous", False)),
            )
            seen.add(user.id)

        # Снять права с тех, кого администрация покинула, пока бот молчал.
        demoted = await self._members.demote_missing_admins(chat_id, seen)

        await self._cache.set(key, sorted(seen), ttl=ADMIN_CACHE_TTL)
        log.info(
            "администраторы синхронизированы",
            extra={"chat_id": chat_id, "admins": len(seen), "demoted": demoted},
        )
        return len(seen)

    async def invalidate(self, chat_id: int) -> None:
        """Сбросить кеш администраторов чата после изменения прав."""
        await self._cache.delete(chat_key(ChatEntity.ADMINS, chat_id))
