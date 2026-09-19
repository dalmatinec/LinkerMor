"""Паспорт модуля владельца."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_owner.handlers import router
from texts.defs import TextDef

TEXTS = [
    TextDef(
        key="owner_health_ok",
        default="Всё работает.\n\n{items}\n\nАктивных чатов: {count}",
        module="owner",
        description="Проверка состояния пройдена",
    ),
    TextDef(
        key="owner_health_failed",
        default="Есть сбои: {reason}\n\n{items}",
        module="owner",
        description="Проверка состояния не пройдена",
    ),
    TextDef(
        key="owner_backup_started",
        default="Создаю копию базы, это займёт несколько секунд.",
        module="owner",
        description="Копия базы создаётся",
    ),
    TextDef(
        key="owner_backup_failed",
        default="Не удалось создать копию: {reason}",
        module="owner",
        description="Копию создать не удалось",
    ),
    TextDef(
        key="owner_chats",
        default="Подключено чатов: {count}, отключено: {reason}\n\n{items}",
        module="owner",
        description="Список подключённых чатов",
    ),
    TextDef(
        key="owner_chats_empty",
        default="Бот пока не добавлен ни в один чат.",
        module="owner",
        description="Чатов нет",
    ),
]

#: Команды владельца работают в личке и не пересекаются с групповыми,
#: но стоят рано: они должны срабатывать при любом состоянии остального.
MODULE = ModuleSpec(
    name="owner",
    priority=15,
    router=router,
    text_defs=tuple(TEXTS),
    can_disable=False,
)
