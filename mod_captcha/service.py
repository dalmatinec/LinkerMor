"""Проверка при входе в чат (ТЗ §10).

Устройство подчинено одному требованию: человек не должен остаться в муте
из-за сбоя бота. Поэтому состояние живёт в базе, а не в памяти, срок
проверки хранится вместе с сессией, и просроченные проверки закрывает
фоновая задача.

Все переходы состояния атомарны. Без этого двойное нажатие кнопки или
два события входа подряд приводили бы к двойному наказанию либо к
проверке, которую невозможно пройти.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from aiogram.types import User
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import BotPermission
from core.logging import get_logger
from mod_captcha.challenges import Challenge, generate
from mod_captcha.models import CaptchaSession
from mod_moderation.models import PunishmentSource
from mod_moderation.service import ModerationService
from permissions.service import PermissionService
from resolver.user_resolver import Target, TargetSource
from settings.service import SettingsService

log = get_logger(__name__)


class Verdict(StrEnum):
    """Чем закончилась попытка."""

    PASSED = "passed"
    WRONG = "wrong"  # ответ неверный, попытки остались
    FAILED = "failed"  # попытки исчерпаны
    EXPIRED = "expired"
    MISSING = "missing"  # проверки нет: истекла или уже пройдена
    FOREIGN = "foreign"  # кнопку нажал не тот, кого проверяют


@dataclass(frozen=True, slots=True)
class StartResult:
    """Результат запуска проверки."""

    started: bool
    challenge: Challenge | None = None
    timeout: int = 0
    #: Проверка уже шла: повторное событие входа ничего не меняет.
    already_running: bool = False


class CaptchaService:
    """Запуск, проверка и закрытие сессий."""

    def __init__(
        self,
        session: AsyncSession,
        settings: SettingsService,
        permissions: PermissionService,
        moderation: ModerationService,
        rng: random.Random | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._permissions = permissions
        self._moderation = moderation
        self._rng = rng or random

    # ─── Запуск ──────────────────────────────────────────────────────────────

    async def start(self, chat_id: int, user: User, *, force: bool = False) -> StartResult:
        """Начать проверку участника.

        Args:
            force: Проверять, даже если в чате она обычно выключена.
                Так поступает защита от налёта: во время всплеска входов
                проверка нужна независимо от обычных настроек.

        Проверка бессмысленна без права ограничивать участников: человек
        мог бы просто писать дальше. В этом случае она пропускается, а не
        имитируется.
        """
        if not force and not await self._settings.get(chat_id, "captcha.enabled"):
            return StartResult(started=False)

        if not await self._permissions.bot_can(chat_id, BotPermission.RESTRICT_MEMBERS):
            log.info(
                "проверка пропущена: нет права ограничивать",
                extra={"chat_id": chat_id, "target_id": user.id},
            )
            return StartResult(started=False)

        kind = str(await self._settings.get(chat_id, "captcha.type"))
        timeout = int(await self._settings.get(chat_id, "captcha.timeout"))
        attempts = int(await self._settings.get(chat_id, "captcha.attempts"))
        challenge = generate(kind, rng=self._rng)

        # Вставка не перезаписывает идущую проверку: два события входа
        # подряд не должны обнулять попытки и продлевать срок.
        stmt = (
            insert(CaptchaSession)
            .values(
                chat_id=chat_id,
                user_id=user.id,
                kind=challenge.kind,
                answer=challenge.answer,
                attempts_left=attempts,
                expires_at=datetime.now(UTC) + timedelta(seconds=timeout),
            )
            .on_conflict_do_nothing(
                index_elements=[CaptchaSession.chat_id, CaptchaSession.user_id]
            )
            .returning(CaptchaSession.user_id)
        )
        claimed = (await self._session.execute(stmt)).scalar_one_or_none()
        if claimed is None:
            return StartResult(started=False, already_running=True)

        # Пока проверка идёт, писать нельзя.
        await self._moderation.mute(
            chat_id,
            None,
            _target(user),
            reason="captcha",
            duration=None,
            source=PunishmentSource.CAPTCHA,
        )

        log.info(
            "проверка начата",
            extra={"chat_id": chat_id, "target_id": user.id, "kind": challenge.kind},
        )
        return StartResult(started=True, challenge=challenge, timeout=timeout)

    async def remember_message(self, chat_id: int, user_id: int, message_id: int) -> None:
        """Запомнить сообщение с проверкой, чтобы потом его убрать."""
        await self._session.execute(
            update(CaptchaSession)
            .where(CaptchaSession.chat_id == chat_id, CaptchaSession.user_id == user_id)
            .values(message_id=message_id)
        )

    # ─── Проверка ответа ─────────────────────────────────────────────────────

    async def verify(self, chat_id: int, user_id: int, value: str) -> tuple[Verdict, int]:
        """Принять ответ.

        Returns:
            Вердикт и число оставшихся попыток.
        """
        stmt = select(CaptchaSession).where(
            CaptchaSession.chat_id == chat_id, CaptchaSession.user_id == user_id
        )
        session_row = (await self._session.execute(stmt)).scalars().first()
        if session_row is None:
            return Verdict.MISSING, 0

        if session_row.expires_at <= datetime.now(UTC):
            await self._close(chat_id, user_id)
            return Verdict.EXPIRED, 0

        if value == session_row.answer:
            # Удаление атомарно: при двойном нажатии выигрывает первое,
            # второе получит MISSING и ничего не сделает повторно.
            deleted = await self._close(chat_id, user_id)
            if not deleted:
                return Verdict.MISSING, 0
            await self._release(chat_id, user_id)
            log.info("проверка пройдена", extra={"chat_id": chat_id, "target_id": user_id})
            return Verdict.PASSED, 0

        # Неверный ответ: уменьшаем счётчик одним запросом.
        remaining = (
            await self._session.execute(
                update(CaptchaSession)
                .where(
                    CaptchaSession.chat_id == chat_id,
                    CaptchaSession.user_id == user_id,
                    CaptchaSession.attempts_left > 1,
                )
                .values(attempts_left=CaptchaSession.attempts_left - 1)
                .returning(CaptchaSession.attempts_left)
            )
        ).scalar_one_or_none()

        if remaining is not None:
            return Verdict.WRONG, int(remaining)

        await self._close(chat_id, user_id)
        await self.punish(chat_id, user_id)
        return Verdict.FAILED, 0

    # ─── Завершение ──────────────────────────────────────────────────────────

    async def punish(self, chat_id: int, user_id: int) -> None:
        """Применить действие, настроенное для непройденной проверки."""
        action = str(await self._settings.get(chat_id, "captcha.fail_action"))
        target = Target(id=user_id, display_name=str(user_id), source=TargetSource.USER_ID)

        if action == "ban":
            await self._moderation.ban(chat_id, None, target, reason="captcha",
                                       source=PunishmentSource.CAPTCHA)
        elif action == "kick":
            await self._moderation.kick(chat_id, None, target, reason="captcha",
                                        source=PunishmentSource.CAPTCHA)
        else:
            # Мут уже стоит с начала проверки: снимать его не нужно.
            pass

        log.info(
            "проверка не пройдена",
            extra={"chat_id": chat_id, "target_id": user_id, "action": action},
        )

    async def collect_expired(self, limit: int = 100) -> list[CaptchaSession]:
        """Просроченные проверки для фоновой задачи."""
        stmt = (
            select(CaptchaSession)
            .where(CaptchaSession.expires_at <= datetime.now(UTC))
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def _close(self, chat_id: int, user_id: int) -> bool:
        """Убрать сессию. Возвращает ``True``, если удалил именно этот вызов."""
        result = await self._session.execute(
            delete(CaptchaSession)
            .where(CaptchaSession.chat_id == chat_id, CaptchaSession.user_id == user_id)
            .returning(CaptchaSession.user_id)
        )
        return result.scalar_one_or_none() is not None

    async def _release(self, chat_id: int, user_id: int) -> None:
        """Вернуть участнику право писать."""
        target = Target(id=user_id, display_name=str(user_id), source=TargetSource.USER_ID)
        await self._moderation.unmute(chat_id, None, target)


def _target(user: User) -> Target:
    name = " ".join(filter(None, (user.first_name, user.last_name))) or str(user.id)
    return Target(
        id=user.id, display_name=name, source=TargetSource.USER_ID, username=user.username
    )


def session_values(session_row: CaptchaSession) -> dict[str, Any]:
    """Значения плейсхолдеров для текстов проверки."""
    return {"attempts": str(session_row.attempts_left)}
