"""Проверка при входе (ТЗ §10)."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, Router
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter
from aiogram.types import CallbackQuery, ChatMemberUpdated
from cache.backend import CacheBackend
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from mod_captcha.callbacks import CaptchaAnswer
from mod_captcha.challenges import Challenge
from mod_captcha.models import CaptchaKind
from mod_antiraid.service import RaidService
from mod_captcha.service import CaptchaService, Verdict
from mod_moderation.service import ModerationService
from mod_welcome.service import WelcomeService
from permissions.service import PermissionService
from sender.sender import Sender
from settings.service import SettingsService
from texts.placeholders import chat_values, user_values
from texts.service import TextService
from ui.buttons import ButtonSpec, build_inline, chunk, parse_style

log = get_logger(__name__)

router = Router(name="captcha")


def _service(
    session: AsyncSession,
    bot: Bot,
    settings: SettingsService,
    permissions: PermissionService,
) -> CaptchaService:
    moderation = ModerationService(session, bot, permissions, settings)
    return CaptchaService(session, settings, permissions, moderation)


def _keyboard(challenge: Challenge, user_id: int, button_label: str):
    """Кнопки с вариантами ответа."""
    if challenge.kind == CaptchaKind.BUTTON:
        return build_inline(
            [
                [
                    ButtonSpec(
                        text=button_label,
                        callback_data=CaptchaAnswer(
                            user_id=user_id, value=challenge.answer
                        ).pack(),
                        style=parse_style("green"),
                    )
                ]
            ]
        )

    return build_inline(
        chunk(
            [
                ButtonSpec(
                    text=option,
                    callback_data=CaptchaAnswer(user_id=user_id, value=option).pack(),
                )
                for option in challenge.options
            ],
            2,
        )
    )


@router.chat_member(
    InGroup(), ModuleEnabled("captcha"), ChatMemberUpdatedFilter(JOIN_TRANSITION)
)
async def on_join(
    event: ChatMemberUpdated,
    session: AsyncSession,
    bot: Bot,
    cache: CacheBackend,
    settings: SettingsService,
    permissions: PermissionService,
    texts: TextService,
    sender: Sender,
) -> None:
    """Начать проверку вошедшего."""
    user = event.new_chat_member.user
    if user.is_bot:
        return

    # Во время налёта проверка обязательна, даже если обычно выключена.
    during_raid = await RaidService(session, cache, settings).is_active(event.chat.id)

    service = _service(session, bot, settings, permissions)
    result = await service.start(event.chat.id, user, force=during_raid)
    if not result.started or result.challenge is None:
        return

    values: dict[str, Any] = {
        "question": result.challenge.question,
        "duration": str(result.timeout),
    }
    values.update(chat_values(event.chat))
    values.update(user_values(user))

    text_key = "captcha_math" if result.challenge.kind == CaptchaKind.MATH else (
        "captcha_emoji" if result.challenge.kind == CaptchaKind.EMOJI else "captcha_button"
    )
    body = await texts.render(event.chat.id, text_key, values)
    label = (await texts.render(event.chat.id, "captcha_btn_confirm", values)).text

    sent = await sender.send(
        event.chat.id, body, reply_markup=_keyboard(result.challenge, user.id, label)
    )
    if sent is not None:
        await service.remember_message(event.chat.id, user.id, sent.message_id)


@router.callback_query(CaptchaAnswer.filter(), InGroup())
async def on_answer(
    callback: CallbackQuery,
    callback_data: CaptchaAnswer,
    session: AsyncSession,
    bot: Bot,
    settings: SettingsService,
    permissions: PermissionService,
    texts: TextService,
    sender: Sender,
) -> None:
    """Принять ответ на проверку.

    Нажатие чужой кнопки отклоняется: иначе проверку за новичка прошёл бы
    любой участник чата.
    """
    message = callback.message
    if message is None:
        return

    chat_id = message.chat.id
    values: dict[str, Any] = {**chat_values(message.chat), **user_values(callback.from_user)}

    if callback.from_user.id != callback_data.user_id:
        answer = await texts.render(chat_id, "captcha_foreign", values)
        await callback.answer(answer.text[:200], show_alert=True)
        return

    service = _service(session, bot, settings, permissions)
    verdict, remaining = await service.verify(chat_id, callback.from_user.id, callback_data.value)
    values["attempts"] = str(remaining)

    if verdict is Verdict.PASSED:
        await sender.delete_message(chat_id, message.message_id)
        await WelcomeService(session, settings, texts, sender).send(
            chat_id, callback.from_user, message.chat
        )
        await callback.answer((await texts.render(chat_id, "captcha_passed", values)).text[:200])
        return

    if verdict is Verdict.WRONG:
        await callback.answer((await texts.render(chat_id, "captcha_wrong", values)).text[:200],
                              show_alert=True)
        return

    if verdict is Verdict.FAILED:
        await sender.delete_message(chat_id, message.message_id)
        await sender.send(chat_id, await texts.render(chat_id, "captcha_failed", values))
        await callback.answer()
        return

    # Проверка истекла или уже закрыта: сообщение больше не актуально.
    await sender.delete_message(chat_id, message.message_id)
    await callback.answer()
