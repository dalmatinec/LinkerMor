"""Паспорт модуля чатов."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_chats.handlers import router
from mod_chats.models import Chat, ChatMember, User

#: Модуль обрабатывает служебные события и обязан идти первым: остальные
#: модули рассчитывают на то, что чат и участник уже есть в базе.
MODULE = ModuleSpec(
    name="chats",
    priority=10,
    router=router,
    models=(Chat, User, ChatMember),
    can_disable=False,  # без него бот не знает о чатах вообще
)
