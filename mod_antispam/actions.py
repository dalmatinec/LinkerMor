"""Применение решения фильтра.

Отделено от правил: правило отвечает на вопрос «нарушение ли это», а
применение — «что с этим делать». Так одно и то же наказание выдаётся
одинаково всеми правилами.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import Message

from core.constants import ActionType
from core.logging import get_logger
from mod_antispam.engine import RuleVerdict
from mod_moderation.models import PunishmentSource
from mod_moderation.service import ModerationService
from resolver.user_resolver import Target, TargetSource
from sender.sender import Sender
from texts.placeholders import chat_values, user_values
from texts.service import TextService

log = get_logger(__name__)


async def apply_verdict(
    message: Message,
    verdict: RuleVerdict,
    moderation: ModerationService,
    texts: TextService,
    sender: Sender,
) -> None:
    """Выполнить решение правила и сообщить нарушителю.

    Порядок важен: сначала удаляется сообщение, затем выдаётся наказание,
    и только потом отправляется объяснение. Иначе объяснение могло бы
    исчезнуть вместе с удалённым сообщением или не дойти до того, кого
    уже исключили.
    """
    user = message.from_user
    if user is None:
        return

    chat_id = message.chat.id
    target = Target(
        id=user.id,
        display_name=" ".join(filter(None, (user.first_name, user.last_name))) or str(user.id),
        source=TargetSource.USER_ID,
        username=user.username,
    )

    if verdict.delete:
        await sender.delete_message(chat_id, message.message_id)

    if verdict.action is ActionType.MUTE:
        await moderation.mute(chat_id, None, target, reason=verdict.rule,
                              duration=verdict.duration, source=PunishmentSource.FILTER)
    elif verdict.action is ActionType.BAN:
        await moderation.ban(chat_id, None, target, reason=verdict.rule,
                             duration=verdict.duration, source=PunishmentSource.FILTER)
    elif verdict.action is ActionType.KICK:
        await moderation.kick(chat_id, None, target, reason=verdict.rule,
                              source=PunishmentSource.FILTER)
    elif verdict.action is ActionType.WARN:
        await moderation.warn(chat_id, None, target, reason=verdict.rule)

    if not verdict.text_key:
        return

    values: dict[str, Any] = dict(verdict.values)
    values.update(chat_values(message.chat))
    values.update(user_values(user))

    await sender.send(chat_id, await texts.render(chat_id, verdict.text_key, values))
