"""Паспорт модуля триггеров."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_triggers.handlers import router
from mod_triggers.models import MessageContent, Trigger
from texts.defs import TextDef

TEXTS = [
    TextDef(
        key="trigger_created",
        default="Триггер «{trigger}» создан.",
        module="triggers",
        description="Триггер добавлен",
    ),
    TextDef(
        key="trigger_deleted",
        default="Триггер «{trigger}» удалён.",
        module="triggers",
        description="Триггер удалён",
    ),
    TextDef(
        key="trigger_not_found",
        default="Триггера «{trigger}» нет в этом чате.",
        module="triggers",
        description="Триггер не найден",
    ),
    TextDef(
        key="trigger_exists",
        default="Триггер «{trigger}» уже существует.",
        module="triggers",
        description="Ключевое слово занято",
    ),
    TextDef(
        key="trigger_needs_reply",
        default=(
            "Ответьте этой командой на сообщение, которое станет ответом триггера, "
            "либо напишите текст ответа со второй строки."
        ),
        module="triggers",
        description="Не указано, чем отвечать",
    ),
    TextDef(
        key="trigger_no_key",
        default="Укажите ключевое слово: /addtrigger привет",
        module="triggers",
        description="Команда вызвана без ключа",
    ),
    TextDef(
        key="trigger_invalid",
        default="Не удалось создать триггер «{trigger}»: {reason}",
        module="triggers",
        description="Ключ или сообщение не подходят",
    ),
    TextDef(
        key="trigger_limit",
        default="В чате уже {count} триггеров, это предел.",
        module="triggers",
        description="Достигнут предел триггеров",
    ),
    TextDef(
        key="trigger_list",
        default="Триггеров в чате: {count}\n\n{trigger}",
        module="triggers",
        description="Список триггеров",
    ),
    TextDef(
        key="trigger_list_empty",
        default="В этом чате нет триггеров.",
        module="triggers",
        description="Список пуст",
    ),
]

#: Триггеры идут после модерации и антиспама: сначала чат защищают, и
#: только потом отвечают на ключевые слова.
MODULE = ModuleSpec(
    name="triggers",
    priority=70,
    router=router,
    models=(MessageContent, Trigger),
    text_defs=tuple(TEXTS),
)
