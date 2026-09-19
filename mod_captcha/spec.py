"""Паспорт модуля проверки при входе."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_captcha.handlers import router
from mod_captcha.models import CaptchaSession
from settings.defs import SettingDef
from texts.defs import TextDef

SETTINGS = [
    SettingDef(
        key="captcha.enabled",
        default=False,
        type=bool,
        module="captcha",
        description="Проверять новых участников при входе",
    ),
    SettingDef(
        key="captcha.type",
        default="button",
        type=str,
        module="captcha",
        description="Вид проверки",
        choices=("button", "math", "emoji"),
    ),
    SettingDef(
        key="captcha.timeout",
        default=120,
        type=int,
        module="captcha",
        description="Сколько секунд даётся на проверку",
        minimum=30,
        maximum=3600,
    ),
    SettingDef(
        key="captcha.attempts",
        default=3,
        type=int,
        module="captcha",
        description="Сколько попыток даётся",
        minimum=1,
        maximum=10,
    ),
    SettingDef(
        key="captcha.fail_action",
        default="mute",
        type=str,
        module="captcha",
        description="Что делать с непрошедшим проверку",
        choices=("mute", "kick", "ban"),
    ),
]

TEXTS = [
    TextDef(
        key="captcha_button",
        default="{mention}, подтвердите, что вы человек. На это есть {duration} секунд.",
        module="captcha",
        description="Проверка одной кнопкой",
    ),
    TextDef(
        key="captcha_math",
        default="{mention}, решите пример: {question}. На это есть {duration} секунд.",
        module="captcha",
        description="Проверка примером",
    ),
    TextDef(
        key="captcha_emoji",
        default="{mention}, выберите символ {question}. На это есть {duration} секунд.",
        module="captcha",
        description="Проверка выбором символа",
    ),
    TextDef(
        key="captcha_btn_confirm",
        default="Я не робот",
        module="captcha",
        description="Подпись кнопки подтверждения",
    ),
    TextDef(
        key="captcha_passed",
        default="Проверка пройдена.",
        module="captcha",
        description="Проверка пройдена",
    ),
    TextDef(
        key="captcha_wrong",
        default="Неверно. Осталось попыток: {attempts}",
        module="captcha",
        description="Ответ неверный, попытки остались",
    ),
    TextDef(
        key="captcha_failed",
        default="{mention} не прошёл проверку.",
        module="captcha",
        description="Попытки исчерпаны",
    ),
    TextDef(
        key="captcha_foreign",
        default="Эта проверка не для вас.",
        module="captcha",
        description="Кнопку нажал посторонний",
    ),
]

#: Проверка идёт сразу после служебных событий: пока она не пройдена,
#: человеку нечего делать в остальных модулях.
MODULE = ModuleSpec(
    name="captcha",
    priority=20,
    router=router,
    models=(CaptchaSession,),
    setting_defs=tuple(SETTINGS),
    text_defs=tuple(TEXTS),
    requires_perms=("can_restrict_members",),
)
