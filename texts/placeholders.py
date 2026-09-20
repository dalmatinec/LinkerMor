"""Единая система плейсхолдеров (ТЗ §14).

Реестр перечисляет всё, что администратор вправе вставить в текст. Он же
служит источником подсказок в панели редактирования и основой проверки:
текст с неизвестным плейсхолдером отклоняется при сохранении, а если такой
всё же встретится в рантайме, он будет вырезан, а не показан человеку.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from texts.entities import Entity, EntityText

#: Значение плейсхолдера: обычная строка либо текст с форматированием.
Value = str | EntityText


@dataclass(frozen=True, slots=True)
class PlaceholderDef:
    """Описание плейсхолдера для проверки и для подсказок в админке."""

    name: str
    group: str
    description: str


def _defs(group: str, items: dict[str, str]) -> list[PlaceholderDef]:
    return [PlaceholderDef(name=n, group=group, description=d) for n, d in items.items()]


REGISTRY: dict[str, PlaceholderDef] = {
    definition.name: definition
    for definition in [
        *_defs(
            "user",
            {
                "user": "Имя пользователя",
                "user_id": "Числовой идентификатор",
                "username": "@username или имя, если username нет",
                "first_name": "Имя",
                "last_name": "Фамилия",
                "mention": "Кликабельное упоминание",
                "messages": "Сколько сообщений написал в этом чате",
            },
        ),
        *_defs(
            "chat",
            {
                "chat": "Название чата",
                "chat_id": "Идентификатор чата",
                "chat_title": "Название чата",
                "chat_username": "@username чата, если он публичный",
                "members_count": "Число участников",
            },
        ),
        *_defs(
            "admin",
            {
                "admin": "Имя администратора, выполнившего действие",
                "admin_id": "Идентификатор администратора",
                "admin_username": "@username администратора",
                "admin_mention": "Кликабельное упоминание администратора",
            },
        ),
        *_defs(
            "action",
            {
                "reason": "Причина действия",
                "duration": "Срок наказания",
                "expires_at": "Когда наказание закончится",
                "time": "Текущее время",
                "date": "Текущая дата",
            },
        ),
        *_defs(
            "moderation",
            {
                "warnings": "Текущее число предупреждений",
                "warn_limit": "Порог предупреждений в этом чате",
            },
        ),
        *_defs(
            "reputation",
            {
                "reputation": "Текущая репутация",
                "delta": "На сколько изменилась репутация",
                "rank": "Текущий ранг",
                "rank_name": "Название текущего ранга",
                "old_rank": "Прежний ранг",
                "new_rank": "Новый ранг",
                "next_rank": "Следующий ранг",
                "to_next_rank": "Сколько осталось до следующего ранга",
            },
        ),
        *_defs(
            "trigger",
            {
                "trigger": "Ключевое слово триггера",
                "count": "Количество",
                "position": "Место в списке",
            },
        ),
        *_defs(
            "game",
            {
                "game": "Название игры",
                "result": "Результат",
                "winner": "Победитель",
                "loser": "Проигравший",
                "bet": "Ставка",
            },
        ),
        *_defs(
            "panel",
            {
                "setting": "Ключ настройки или текста",
                "description": "Пояснение к настройке",
                "value": "Текущее значение",
                "source": "Откуда взят текст: чат, общий или по умолчанию",
                "module": "Название модуля",
                "role": "Кто человек для бота",
                "question": "Задание проверки при входе",
                "attempts": "Сколько попыток осталось",
                "items": "Список: ранги, триггеры, участники",
            },
        ),
        *_defs(
            "stats",
            {
                "messages_today": "Сообщений сегодня",
                "messages_week": "Сообщений за неделю",
                "messages_month": "Сообщений за месяц",
                "active_today": "Писали сегодня",
                "active_week": "Писали за неделю",
                "members_total": "Известно участников",
                "staff_total": "Администрация чата",
                "new_week": "Новых за неделю",
                "bans": "Блокировок за неделю",
                "mutes": "Ограничений за неделю",
                "kicks": "Исключений за неделю",
                "warns_week": "Предупреждений за неделю",
                "filter_actions": "Срабатываний антиспама",
                "chart": "График сообщений по дням",
                "days": "Подписи дней недели к графику",
            },
        ),
        *_defs(
            "system",
            {
                "bot": "Имя бота",
                "bot_username": "@username бота",
                "permission": "Право, которого не хватает боту",
            },
        ),
    ]
}


def known_names() -> frozenset[str]:
    """Все допустимые имена плейсхолдеров."""
    return frozenset(REGISTRY)


def unknown_placeholders(text: EntityText) -> set[str]:
    """Плейсхолдеры текста, которых нет в реестре.

    Вызывается при сохранении текста: администратор сразу узнаёт об
    опечатке, вместо того чтобы обнаружить пустое место в сообщении.
    """
    return text.placeholders() - known_names()


def grouped() -> dict[str, list[PlaceholderDef]]:
    """Плейсхолдеры по группам — для подсказки в панели редактирования."""
    result: dict[str, list[PlaceholderDef]] = {}
    for definition in REGISTRY.values():
        result.setdefault(definition.group, []).append(definition)
    return result


# ─── Построение значений ─────────────────────────────────────────────────────


def mention(user: Any) -> EntityText:
    """Кликабельное упоминание пользователя.

    У пользователя без username упоминание возможно только через entity
    ``text_mention``: текстом «@…» его не позвать.
    """
    name = " ".join(filter(None, (user.first_name, getattr(user, "last_name", None))))
    name = name or str(user.id)
    if getattr(user, "username", None):
        return EntityText(text=f"@{user.username}")
    return EntityText(text=name, entities=(Entity("text_mention", 0, len(name), user_id=user.id),))


def user_values(user: Any, prefix: str = "") -> dict[str, Value]:
    """Значения для пользователя. ``prefix='admin'`` даёт {admin}, {admin_id}…"""
    name = " ".join(filter(None, (user.first_name, getattr(user, "last_name", None))))
    name = name or str(user.id)
    username = getattr(user, "username", None)

    if prefix:
        return {
            prefix: name,
            f"{prefix}_id": str(user.id),
            f"{prefix}_username": f"@{username}" if username else name,
            f"{prefix}_mention": mention(user),
        }
    return {
        "user": name,
        "user_id": str(user.id),
        "username": f"@{username}" if username else name,
        "first_name": user.first_name or "",
        "last_name": getattr(user, "last_name", None) or "",
        "mention": mention(user),
    }


def chat_values(chat: Any, members_count: int | None = None) -> dict[str, Value]:
    """Значения для чата."""
    title = getattr(chat, "title", None) or str(chat.id)
    username = getattr(chat, "username", None)
    values: dict[str, Value] = {
        "chat": title,
        "chat_title": title,
        "chat_id": str(chat.id),
        "chat_username": f"@{username}" if username else title,
    }
    if members_count is not None:
        values["members_count"] = str(members_count)
    return values


def time_values(moment: datetime | None = None) -> dict[str, Value]:
    """Текущие дата и время в виде, пригодном для показа."""
    moment = moment or datetime.now()
    return {"time": moment.strftime("%H:%M"), "date": moment.strftime("%d.%m.%Y")}
