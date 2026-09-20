"""Паспорт модуля статистики."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_stats.handlers import router
from mod_stats.models import DailyActivity
from texts.defs import TextDef

TEXTS = [
    TextDef(
        key="stats_report",
        default=(
            "Сводка по чату «{chat_title}»\n"
            "\n"
            "Сообщения\n"
            "сегодня: {messages_today}\n"
            "за неделю: {messages_week}\n"
            "за месяц: {messages_month}\n"
            "\n"
            "{chart}\n"
            "{days}\n"
            "\n"
            "Участники\n"
            "писали сегодня: {active_today}\n"
            "писали за неделю: {active_week}\n"
            "новых за неделю: {new_week}\n"
            "всего известно: {members_total}\n"
            "администрация: {staff_total}\n"
            "\n"
            "Модерация за неделю\n"
            "блокировок: {bans}\n"
            "ограничений: {mutes}\n"
            "предупреждений: {warns_week}\n"
            "сработал антиспам: {filter_actions}\n"
            "\n"
            "Самые активные за неделю\n"
            "{items}"
        ),
        module="stats",
        description="Сводка по чату. Меняйте оформление как угодно",
    ),
]

#: Статистика собирается middleware активности, поэтому модуль отвечает
#: только за показ сводки и идёт последним.
MODULE = ModuleSpec(
    name="stats",
    priority=95,
    router=router,
    models=(DailyActivity,),
    text_defs=tuple(TEXTS),
)
