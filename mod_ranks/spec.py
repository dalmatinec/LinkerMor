"""Паспорт модуля рангов."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_ranks.handlers import router
from mod_ranks.models import Rank, UserRank
from settings.defs import SettingDef
from texts.defs import TextDef

SETTINGS = [
    SettingDef(
        key="ranks.metric",
        default="reputation",
        type=str,
        module="ranks",
        description="По какому показателю считается ранг",
        choices=("reputation", "messages", "sum"),
    ),
    SettingDef(
        key="ranks.notify",
        default=True,
        type=bool,
        module="ranks",
        description="Сообщать в чат о смене ранга",
    ),
]

TEXTS = [
    TextDef(
        key="rank_up",
        default="{mention} получает ранг «{new_rank}»!",
        module="ranks",
        description="Участник поднялся на ступень",
    ),
    TextDef(
        key="rank_down",
        default="{mention} опускается до ранга «{new_rank}».",
        module="ranks",
        description="Участник опустился на ступень",
    ),
    TextDef(
        key="rank_show",
        default="Ранг {user}: «{rank}». До ранга «{next_rank}» осталось {to_next_rank}.",
        module="ranks",
        description="Показ ранга участника",
    ),
    TextDef(
        key="rank_none",
        default="У {user} пока нет ранга. Показатель: {count}",
        module="ranks",
        description="Ранг ещё не достигнут",
    ),
    TextDef(
        key="rank_list",
        default="Ранги чата:\n\n{items}",
        module="ranks",
        description="Список ступеней",
    ),
    TextDef(
        key="rank_list_empty",
        default="В этом чате ранги не настроены.",
        module="ranks",
        description="Ступеней нет",
    ),
    TextDef(
        key="rank_added",
        default="Ранг «{rank}» добавлен с порогом {count}.",
        module="ranks",
        description="Ступень создана",
    ),
    TextDef(
        key="rank_deleted",
        default="Ранг «{rank}» удалён.",
        module="ranks",
        description="Ступень удалена",
    ),
    TextDef(
        key="rank_not_found",
        default="Ранга «{rank}» в этом чате нет.",
        module="ranks",
        description="Ступень не найдена",
    ),
    TextDef(
        key="rank_exists",
        default="Ранг с таким названием или порогом уже есть.",
        module="ranks",
        description="Название или порог заняты",
    ),
    TextDef(
        key="rank_usage",
        default="Укажите порог и название: /addrank 100 Ветеран",
        module="ranks",
        description="Команда вызвана неверно",
    ),
]

#: Ранги пересчитываются последними: к этому моменту репутация и счётчик
#: сообщений уже обновлены.
MODULE = ModuleSpec(
    name="ranks",
    priority=85,
    router=router,
    models=(Rank, UserRank),
    setting_defs=tuple(SETTINGS),
    text_defs=tuple(TEXTS),
)
