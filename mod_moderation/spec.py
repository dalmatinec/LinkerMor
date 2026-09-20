"""Паспорт модуля модерации."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_moderation.handlers import router
from mod_moderation.models import Punishment, Warning
from settings.defs import SettingDef
from texts.defs import TextDef

SETTINGS = [
    SettingDef(
        key="moderation.warn_limit",
        default=3,
        type=int,
        module="moderation",
        description="Сколько предупреждений можно получить до наказания",
        minimum=1,
        maximum=20,
    ),
    SettingDef(
        key="moderation.warn_action",
        default="mute",
        type=str,
        module="moderation",
        description="Что происходит при исчерпании предупреждений",
        choices=("mute", "ban", "kick"),
    ),
    SettingDef(
        key="moderation.warn_duration",
        default=86400,
        type=int,
        module="moderation",
        description="Срок наказания за исчерпанные предупреждения, в секундах",
        minimum=0,
        maximum=31536000,
    ),
    SettingDef(
        key="moderation.warn_expire_days",
        default=30,
        type=int,
        module="moderation",
        description="Через сколько дней предупреждение перестаёт учитываться",
        minimum=0,
        maximum=3650,
    ),
]

TEXTS = [
    TextDef(
        key="ban_success",
        default="{mention} заблокирован. Срок: {duration}. Причина: {reason}",
        module="moderation",
        description="Участник заблокирован",
    ),
    TextDef(
        key="unban_success",
        default="{mention} разблокирован.",
        module="moderation",
        description="Блокировка снята",
    ),
    TextDef(
        key="not_banned",
        default="{mention} не заблокирован.",
        module="moderation",
        description="Попытка снять несуществующую блокировку",
    ),
    TextDef(
        key="mute_success",
        default="{mention} не может писать. Срок: {duration}. Причина: {reason}",
        module="moderation",
        description="Участнику запрещено писать",
    ),
    TextDef(
        key="unmute_success",
        default="{mention} снова может писать.",
        module="moderation",
        description="Ограничение снято",
    ),
    TextDef(
        key="not_muted",
        default="{mention} не ограничен в правах.",
        module="moderation",
        description="Попытка снять несуществующее ограничение",
    ),
    TextDef(
        key="kick_success",
        default="{mention} удалён из чата и может вернуться по ссылке.",
        module="moderation",
        description="Участник исключён из чата",
    ),
    TextDef(
        key="warn_success",
        default="{mention} получает предупреждение {warnings} из {warn_limit}. "
        "Причина: {reason}",
        module="moderation",
        description="Выдано предупреждение",
    ),
    TextDef(
        key="warn_limit_reached",
        default="{mention} исчерпал предупреждения и наказан на срок: {duration}",
        module="moderation",
        description="Предупреждения исчерпаны, применено наказание",
    ),
    TextDef(
        key="unwarn_success",
        default="С {mention} снято предупреждение. Осталось: {warnings} из {warn_limit}",
        module="moderation",
        description="Предупреждение снято",
    ),
    TextDef(
        key="no_warnings",
        default="У {mention} нет действующих предупреждений.",
        module="moderation",
        description="Предупреждений нет",
    ),
    TextDef(
        key="warns_list",
        default="У {mention} действует предупреждений: {warnings} из {warn_limit}",
        module="moderation",
        description="Сколько предупреждений у участника",
    ),
    TextDef(
        key="moderation_failed",
        default="Не удалось применить меру к {mention}. Проверьте права бота.",
        module="moderation",
        description="Telegram отклонил действие",
    ),
]

#: Модерация идёт после служебных событий, но раньше контента: команда
#: администратора не должна попадать под фильтры и триггеры.
MODULE = ModuleSpec(
    name="moderation",
    priority=50,
    router=router,
    models=(Punishment, Warning),
    setting_defs=tuple(SETTINGS),
    text_defs=tuple(TEXTS),
    requires_perms=("can_restrict_members",),
)
