"""Бизнес-логика модерации (ТЗ §7).

Сервис принимает решение и меняет состояние, но ничего не отправляет: он
возвращает ключ текста и значения для подстановки, а отправкой занимается
хендлер. Благодаря этому одну и ту же меру можно применить из команды, из
фильтра антиспама и из капчи, не дублируя логику.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import BotPermission
from core.logging import get_logger
from mod_moderation.actions import ModerationActions
from mod_moderation.models import Punishment, PunishmentSource, PunishmentType
from mod_moderation.repo import PunishmentRepository, WarningRepository
from permissions.service import PermissionService
from resolver.duration import format_duration
from resolver.user_resolver import Target
from texts.entities import Entity, EntityText
from settings.service import SettingsService

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModerationResult:
    """Что произошло и что сказать людям.

    Attributes:
        text_key: Ключ текста для ответа.
        values: Значения плейсхолдеров.
        punishment: Созданная запись, если мера была применена.
        succeeded: Удалось ли выполнить действие в Telegram.
    """

    text_key: str
    values: dict[str, Any] = field(default_factory=dict)
    punishment: Punishment | None = None
    succeeded: bool = True


class ModerationService:
    """Выдача и снятие наказаний."""

    def __init__(
        self,
        session: AsyncSession,
        bot: Bot,
        permissions: PermissionService,
        settings: SettingsService,
    ) -> None:
        self._session = session
        self._permissions = permissions
        self._settings = settings
        self._actions = ModerationActions(bot)
        self._punishments = PunishmentRepository(session)
        self._warnings = WarningRepository(session)

    # ─── Блокировка ──────────────────────────────────────────────────────────

    async def ban(
        self,
        chat_id: int,
        actor_id: int,
        target: Target,
        reason: str | None = None,
        duration: timedelta | None = None,
        source: PunishmentSource = PunishmentSource.MANUAL,
    ) -> ModerationResult:
        """Заблокировать участника или канал-отправитель."""
        await self._permissions.require_bot_permission(chat_id, BotPermission.RESTRICT_MEMBERS)
        if not target.is_chat:
            await self._permissions.require_can_act_on(chat_id, actor_id, target.id)

        until = datetime.now(UTC) + duration if duration else None
        ok = await self._actions.ban(chat_id, target.id, until=until, is_chat=target.is_chat)
        if not ok:
            return ModerationResult("moderation_failed", self._values(target, reason, duration),
                                    succeeded=False)

        punishment = await self._punishments.create(
            chat_id=chat_id,
            user_id=target.id,
            type_=PunishmentType.BAN,
            actor_id=actor_id,
            reason=reason,
            until=until,
            source=source,
            is_chat_target=target.is_chat,
        )
        log.info(
            "выдан бан",
            extra={"chat_id": chat_id, "target_id": target.id, "actor": actor_id,
                   "until": str(until), "source": source},
        )
        return ModerationResult("ban_success", self._values(target, reason, duration), punishment)

    async def unban(self, chat_id: int, actor_id: int, target: Target) -> ModerationResult:
        await self._permissions.require_bot_permission(chat_id, BotPermission.RESTRICT_MEMBERS)

        ok = await self._actions.unban(chat_id, target.id, is_chat=target.is_chat)
        removed = await self._punishments.deactivate(
            chat_id, target.id, PunishmentType.BAN, revoked_by=actor_id
        )
        if not ok and not removed:
            return ModerationResult("not_banned", self._values(target), succeeded=False)

        log.info("снят бан", extra={"chat_id": chat_id, "target_id": target.id, "actor": actor_id})
        return ModerationResult("unban_success", self._values(target))

    # ─── Ограничение ─────────────────────────────────────────────────────────

    async def mute(
        self,
        chat_id: int,
        actor_id: int,
        target: Target,
        reason: str | None = None,
        duration: timedelta | None = None,
        source: PunishmentSource = PunishmentSource.MANUAL,
    ) -> ModerationResult:
        """Запретить участнику писать в чат."""
        await self._permissions.require_bot_permission(chat_id, BotPermission.RESTRICT_MEMBERS)
        await self._permissions.require_can_act_on(chat_id, actor_id, target.id)

        until = datetime.now(UTC) + duration if duration else None
        if not await self._actions.mute(chat_id, target.id, until=until):
            return ModerationResult("moderation_failed", self._values(target, reason, duration),
                                    succeeded=False)

        punishment = await self._punishments.create(
            chat_id=chat_id,
            user_id=target.id,
            type_=PunishmentType.MUTE,
            actor_id=actor_id,
            reason=reason,
            until=until,
            source=source,
        )
        log.info(
            "выдан мут",
            extra={"chat_id": chat_id, "target_id": target.id, "actor": actor_id,
                   "until": str(until), "source": source},
        )
        return ModerationResult("mute_success", self._values(target, reason, duration), punishment)

    async def unmute(self, chat_id: int, actor_id: int, target: Target) -> ModerationResult:
        await self._permissions.require_bot_permission(chat_id, BotPermission.RESTRICT_MEMBERS)

        ok = await self._actions.unmute(chat_id, target.id)
        removed = await self._punishments.deactivate(
            chat_id, target.id, PunishmentType.MUTE, revoked_by=actor_id
        )
        if not ok and not removed:
            return ModerationResult("not_muted", self._values(target), succeeded=False)

        log.info("снят мут", extra={"chat_id": chat_id, "target_id": target.id, "actor": actor_id})
        return ModerationResult("unmute_success", self._values(target))

    async def kick(
        self,
        chat_id: int,
        actor_id: int,
        target: Target,
        reason: str | None = None,
        source: PunishmentSource = PunishmentSource.MANUAL,
    ) -> ModerationResult:
        """Удалить из чата с правом вернуться.

        Команды для этого нет: действие применяется капчей и фильтрами.
        """
        await self._permissions.require_bot_permission(chat_id, BotPermission.RESTRICT_MEMBERS)
        await self._permissions.require_can_act_on(chat_id, actor_id, target.id)

        if not await self._actions.kick(chat_id, target.id):
            return ModerationResult("moderation_failed", self._values(target, reason),
                                    succeeded=False)

        punishment = await self._punishments.create(
            chat_id=chat_id,
            user_id=target.id,
            type_=PunishmentType.KICK,
            actor_id=actor_id,
            reason=reason,
            until=None,
            source=source,
        )
        # Исключение не длится: запись нужна только для истории.
        await self._punishments.deactivate(chat_id, target.id, PunishmentType.KICK)
        log.info("исключён из чата", extra={"chat_id": chat_id, "target_id": target.id,
                                            "actor": actor_id, "source": source})
        return ModerationResult("kick_success", self._values(target, reason), punishment)

    # ─── Предупреждения ──────────────────────────────────────────────────────

    async def warn(
        self,
        chat_id: int,
        actor_id: int,
        target: Target,
        reason: str | None = None,
    ) -> ModerationResult:
        """Выдать предупреждение и наказать при достижении порога.

        Строка участника блокируется на время операции: два администратора
        могут выдать предупреждение одновременно, и без блокировки оба
        увидели бы одинаковый счёт, а наказание не сработало бы.
        """
        await self._permissions.require_can_act_on(chat_id, actor_id, target.id)

        await self._warnings.lock_member(chat_id, target.id)

        expire_days = int(await self._settings.get(chat_id, "moderation.warn_expire_days"))
        expires_at = datetime.now(UTC) + timedelta(days=expire_days) if expire_days else None
        await self._warnings.add(
            chat_id=chat_id,
            user_id=target.id,
            actor_id=actor_id,
            reason=reason,
            expires_at=expires_at,
        )

        count = await self._warnings.count_active(chat_id, target.id)
        limit = int(await self._settings.get(chat_id, "moderation.warn_limit"))
        values = self._values(target, reason)
        values.update(warnings=str(count), warn_limit=str(limit))

        if count < limit:
            log.info(
                "выдано предупреждение",
                extra={"chat_id": chat_id, "target_id": target.id, "actor": actor_id,
                       "count": count, "limit": limit},
            )
            return ModerationResult("warn_success", values)

        return await self._escalate(chat_id, actor_id, target, values)

    async def _escalate(
        self, chat_id: int, actor_id: int, target: Target, values: dict[str, Any]
    ) -> ModerationResult:
        """Применить меру за исчерпанные предупреждения."""
        action = str(await self._settings.get(chat_id, "moderation.warn_action"))
        seconds = int(await self._settings.get(chat_id, "moderation.warn_duration"))
        duration = timedelta(seconds=seconds) if seconds else None

        # Счёт обнуляется: иначе следующее предупреждение снова превысит порог.
        await self._warnings.revoke_all(chat_id, target.id, revoked_by=None)

        if action == "ban":
            await self.ban(chat_id, actor_id, target, "warn limit", duration,
                           source=PunishmentSource.WARN)
        elif action == "kick":
            await self.kick(chat_id, actor_id, target, "warn limit",
                            source=PunishmentSource.WARN)
        else:
            await self.mute(chat_id, actor_id, target, "warn limit", duration,
                            source=PunishmentSource.WARN)

        values["duration"] = format_duration(duration)
        log.info(
            "предупреждения исчерпаны",
            extra={"chat_id": chat_id, "target_id": target.id, "action": action},
        )
        return ModerationResult("warn_limit_reached", values)

    async def unwarn(self, chat_id: int, actor_id: int, target: Target) -> ModerationResult:
        """Снять последнее предупреждение.

        Роль проверяется фильтром хендлера, поэтому здесь дополнительной
        проверки нет: снятие предупреждения безопаснее его выдачи.
        """
        if not await self._warnings.revoke_last(chat_id, target.id, revoked_by=actor_id):
            return ModerationResult("no_warnings", self._values(target), succeeded=False)

        count = await self._warnings.count_active(chat_id, target.id)
        limit = int(await self._settings.get(chat_id, "moderation.warn_limit"))
        values = self._values(target)
        values.update(warnings=str(count), warn_limit=str(limit))

        log.info("снято предупреждение", extra={"chat_id": chat_id, "target_id": target.id,
                                                "actor": actor_id})
        return ModerationResult("unwarn_success", values)

    async def warnings_of(self, chat_id: int, target: Target) -> ModerationResult:
        """Показать действующие предупреждения участника."""
        count = await self._warnings.count_active(chat_id, target.id)
        limit = int(await self._settings.get(chat_id, "moderation.warn_limit"))
        values = self._values(target)
        values.update(warnings=str(count), warn_limit=str(limit))
        return ModerationResult("warns_list" if count else "no_warnings", values)

    # ─── Вспомогательное ─────────────────────────────────────────────────────

    @staticmethod
    def _mention(target: Target) -> EntityText | str:
        """Кликабельное упоминание цели.

        У пользователя без username упоминание возможно только через entity
        ``text_mention``; для канала-отправителя упоминания нет вовсе.
        """
        if target.is_chat:
            return target.display_name
        if target.username:
            return EntityText(text=f"@{target.username}")
        name = target.display_name
        return EntityText(
            text=name, entities=(Entity("text_mention", 0, len(name), user_id=target.id),)
        )

    @classmethod
    def _values(
        cls, target: Target, reason: str | None = None, duration: timedelta | None = None
    ) -> dict[str, Any]:
        """Значения плейсхолдеров, общие для всех ответов модерации."""
        return {
            "user": target.display_name,
            "user_id": str(target.id),
            "username": target.mention_name,
            "mention": cls._mention(target),
            "reason": reason or "",
            "duration": format_duration(duration),
        }
