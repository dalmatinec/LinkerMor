"""Паспорт модуля приветствия."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_welcome.handlers import router
from mod_welcome.models import WelcomeMessage
from settings.defs import SettingDef
from texts.defs import TextDef

SETTINGS = [
    SettingDef(
        key="welcome.enabled",
        default=False,
        type=bool,
        module="welcome",
        description="Приветствовать новых участников",
    ),
    SettingDef(
        key="welcome.delete_previous",
        default=True,
        type=bool,
        module="welcome",
        description="Удалять прошлое приветствие при новом входе",
    ),
]

TEXTS = [
    TextDef(
        key="welcome_default",
        default="Добро пожаловать, {mention}! Прочитайте правила чата.",
        module="welcome",
        description="Приветствие, пока своё не задано",
    ),
    TextDef(
        key="welcome_saved",
        default="Приветствие сохранено.",
        module="welcome",
        description="Приветствие изменено",
    ),
    TextDef(
        key="welcome_deleted",
        default="Приветствие удалено, будет использоваться стандартное.",
        module="welcome",
        description="Приветствие сброшено",
    ),
    TextDef(
        key="welcome_not_set",
        default="Своё приветствие не настроено.",
        module="welcome",
        description="Нечего удалять",
    ),
    TextDef(
        key="welcome_needs_reply",
        default="Ответьте этой командой на сообщение, которое станет приветствием.",
        module="welcome",
        description="Команда вызвана без ответа на сообщение",
    ),
    TextDef(
        key="welcome_invalid",
        default="Не удалось сохранить приветствие: {reason}",
        module="welcome",
        description="Сообщение не подходит",
    ),
]

#: Приветствие идёт после проверки при входе: сначала человека проверяют,
#: и только потом здороваются.
MODULE = ModuleSpec(
    name="welcome",
    priority=25,
    router=router,
    models=(WelcomeMessage,),
    setting_defs=tuple(SETTINGS),
    text_defs=tuple(TEXTS),
)
