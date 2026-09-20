"""Паспорт модуля репутации."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_reputation.handlers import router
from mod_reputation.models import Reputation, ReputationChange
from settings.defs import SettingDef
from texts.defs import TextDef

SETTINGS = [
    SettingDef(
        key="reputation.enabled",
        default=True,
        type=bool,
        module="reputation",
        description="Менять репутацию ответом на сообщение",
    ),
    SettingDef(
        key="reputation.words_plus",
        default="+,спасибо,спс,благодарю,thanks",
        type=str,
        module="reputation",
        description="Слова, повышающие репутацию, через запятую",
    ),
    SettingDef(
        key="reputation.words_minus",
        default="-",
        type=str,
        module="reputation",
        description="Слова, понижающие репутацию, через запятую",
    ),
    SettingDef(
        key="reputation.allow_minus",
        default=True,
        type=bool,
        module="reputation",
        description="Разрешать понижать репутацию",
    ),
    SettingDef(
        key="reputation.cooldown",
        default=3600,
        type=int,
        module="reputation",
        description="Пауза между изменениями одной и той же паре, в секундах",
        minimum=0,
        maximum=604800,
    ),
    SettingDef(
        key="reputation.daily_limit",
        default=10,
        type=int,
        module="reputation",
        description="Сколько раз в сутки один человек может менять репутацию",
        minimum=0,
        maximum=1000,
    ),
]

TEXTS = [
    TextDef(
        key="reputation_given",
        default="{mention} получает +1 к репутации. Теперь: {reputation}",
        module="reputation",
        description="Репутация повышена",
    ),
    TextDef(
        key="reputation_taken",
        default="{mention} теряет 1 репутации. Теперь: {reputation}",
        module="reputation",
        description="Репутация понижена",
    ),
    TextDef(
        key="reputation_self",
        default="Менять репутацию себе нельзя.",
        module="reputation",
        description="Попытка изменить репутацию самому себе",
    ),
    TextDef(
        key="reputation_cooldown",
        default="Вы уже отмечали этого участника. Подождите {duration}.",
        module="reputation",
        description="Не прошла пауза между изменениями",
    ),
    TextDef(
        key="reputation_limit",
        default="На сегодня предел: {count} изменений репутации.",
        module="reputation",
        description="Исчерпан дневной предел",
    ),
    TextDef(
        key="reputation_minus_disabled",
        default="Понижать репутацию в этом чате нельзя.",
        module="reputation",
        description="Понижение выключено",
    ),
    TextDef(
        key="reputation_show",
        default="Репутация {user}: {reputation}. Место в чате: {position}",
        module="reputation",
        description="Показ репутации участника",
    ),
    TextDef(
        key="reputation_top",
        default="Участники с наибольшей репутацией:\n\n{items}",
        module="reputation",
        description="Список лучших",
    ),
    TextDef(
        key="reputation_top_empty",
        default="Репутацию в этом чате пока никто не получал.",
        module="reputation",
        description="Список пуст",
    ),
]

#: Репутация считается после модерации и триггеров: это пассивный сбор,
#: который не должен мешать более важным реакциям.
MODULE = ModuleSpec(
    name="reputation",
    priority=80,
    router=router,
    models=(Reputation, ReputationChange),
    setting_defs=tuple(SETTINGS),
    text_defs=tuple(TEXTS),
)
