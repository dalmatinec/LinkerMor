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
        key="owner_broadcast_prompt",
        default=(
            "Пришлите сообщение для рассылки администраторам чатов.\n\n"
            "Форматирование и премиум-эмодзи сохранятся.\n\nОтменить: /cancel"
        ),
        module="owner",
        description="Запрос сообщения для рассылки",
    ),
    TextDef(
        key="owner_broadcast_confirm",
        default="Разослать это сообщение? Получателей: {count}",
        module="owner",
        description="Подтверждение рассылки",
    ),
    TextDef(
        key="owner_broadcast_empty",
        default="Пустое сообщение разослать нельзя.",
        module="owner",
        description="Сообщение без текста",
    ),
    TextDef(
        key="owner_broadcast_done",
        default="Рассылка выполнена. Доставлено: {count}, не доставлено: {reason}",
        module="owner",
        description="Итог рассылки",
    ),
    TextDef(
        key="owner_broadcast_cancelled",
        default="Рассылка отменена.",
        module="owner",
        description="Рассылка отменена",
    ),
    TextDef(key="owner_broadcast_btn_send", default="Разослать", module="owner",
            description="Кнопка: подтвердить рассылку"),
    TextDef(key="owner_broadcast_btn_cancel", default="Отмена", module="owner",
            description="Кнопка: отменить рассылку"),
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
