"""Паспорт модуля защиты от налётов."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_antiraid.handlers import router
from mod_antiraid.models import RaidEvent
from settings.defs import SettingDef
from texts.defs import TextDef

SETTINGS = [
    SettingDef(
        key="antiraid.enabled",
        default=True,
        type=bool,
        module="antiraid",
        description="Замечать массовый вход и защищать чат",
    ),
    SettingDef(
        key="antiraid.join_limit",
        default=10,
        type=int,
        module="antiraid",
        description="Сколько входов за период считается налётом",
        minimum=3,
        maximum=200,
    ),
    SettingDef(
        key="antiraid.window",
        default=30,
        type=int,
        module="antiraid",
        description="Период наблюдения за входами, в секундах",
        minimum=5,
        maximum=600,
    ),
    SettingDef(
        key="antiraid.duration",
        default=600,
        type=int,
        module="antiraid",
        description="Сколько длится тревога, в секундах",
        minimum=60,
        maximum=86400,
    ),
    SettingDef(
        key="antiraid.action",
        default="captcha",
        type=str,
        module="antiraid",
        description="Что делать с входящими во время тревоги",
        choices=("captcha", "mute", "kick", "ban"),
    ),
    SettingDef(
        key="antiraid.notify",
        default=True,
        type=bool,
        module="antiraid",
        description="Сообщать в чат о начале тревоги",
    ),
]

TEXTS = [
    TextDef(
        key="antiraid_started",
        default=(
            "Замечен массовый вход: {count} человек подряд. "
            "Включена защита чата."
        ),
        module="antiraid",
        description="Тревога включилась сама",
    ),
    TextDef(
        key="antiraid_status_on",
        default="Защита от налёта включена. Мера: {reason}",
        module="antiraid",
        description="Состояние: тревога действует",
    ),
    TextDef(
        key="antiraid_status_off",
        default="Защита от налёта не действует, чат в обычном режиме.",
        module="antiraid",
        description="Состояние: тревоги нет",
    ),
    TextDef(
        key="antiraid_manual_on",
        default="Защита включена вручную. Мера: {reason}",
        module="antiraid",
        description="Тревогу включил администратор",
    ),
    TextDef(
        key="antiraid_manual_off",
        default="Защита снята, чат вернулся в обычный режим.",
        module="antiraid",
        description="Тревогу снял администратор",
    ),
]

#: Защита от налёта идёт раньше проверки при входе: она решает, нужна ли
#: проверка вообще и не выставить ли входящего сразу.
MODULE = ModuleSpec(
    name="antiraid",
    priority=18,
    router=router,
    models=(RaidEvent,),
    setting_defs=tuple(SETTINGS),
    text_defs=tuple(TEXTS),
    requires_perms=("can_restrict_members",),
)
