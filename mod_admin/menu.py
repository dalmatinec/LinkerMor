"""Построение экранов админ-панели.

Панель динамическая: состав пунктов зависит от того, какие модули
подключены, какие из них включены в этом чате и какая роль у человека.
Выключенный модуль не показывает своих настроек вовсе.

Подписи кнопок — такие же настраиваемые тексты, как и всё остальное:
владелец бота может их переписать и поставить премиум-эмодзи.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.registry import ModuleRegistry
from mod_admin.callbacks import (
    ChatChoice,
    ListAction,
    ModuleAction,
    Nav,
    SettingAction,
    TextAction,
    WelcomeAction,
)
from settings.defs import SettingDef, SettingsRegistry, module_toggle_key
from settings.service import SettingsService
from texts.defs import TextDef, TextRegistry
from texts.service import TextService
from ui.buttons import ButtonSpec, parse_style

#: Сколько элементов показывать на одном экране.
PAGE_SIZE = 8

#: Предел длины подписи кнопки в Telegram.
BUTTON_LIMIT = 64


@dataclass(slots=True)
class Screen:
    """Экран панели: текст сообщения и клавиатура."""

    text_key: str
    values: dict[str, Any] = field(default_factory=dict)
    rows: list[list[ButtonSpec]] = field(default_factory=list)


async def label(texts: TextService, chat_id: int | None, key: str, **values: Any) -> str:
    """Подпись кнопки из системы текстов."""
    rendered = await texts.render(chat_id, key, values)
    return rendered.text


async def back_button(texts: TextService, chat_id: int | None, screen: str) -> ButtonSpec:
    return ButtonSpec(
        text=await label(texts, chat_id, "admin_btn_back"),
        callback_data=Nav(screen=screen).pack(),
    )


def paginate(items: list, page: int) -> tuple[list, int, int]:
    """Срез страницы и её координаты."""
    total = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total - 1))
    start = page * PAGE_SIZE
    return items[start : start + PAGE_SIZE], page, total


async def pager_row(
    texts: TextService, chat_id: int | None, screen: str, page: int, total: int
) -> list[ButtonSpec]:
    """Кнопки перелистывания, если страниц больше одной."""
    if total <= 1:
        return []
    row: list[ButtonSpec] = []
    if page > 0:
        row.append(
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_prev"),
                callback_data=Nav(screen=screen, page=page - 1).pack(),
            )
        )
    if page < total - 1:
        row.append(
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_next"),
                callback_data=Nav(screen=screen, page=page + 1).pack(),
            )
        )
    return row


# ─── Экраны ──────────────────────────────────────────────────────────────────


async def chat_list_screen(texts: TextService, chats: list, page: int = 0) -> Screen:
    """Список чатов, доступных этому администратору.

    Показываются только те, где у человека есть права: чужие чаты в панели
    не появляются даже при прямом переходе.
    """
    if not chats:
        return Screen(text_key="admin_no_chats")

    visible, page, total = paginate(chats, page)
    rows = [
        [
            ButtonSpec(
                text=chat.title or str(chat.chat_id),
                callback_data=ChatChoice(chat_id=chat.chat_id).pack(),
            )
        ]
        for chat in visible
    ]
    pager = await pager_row(texts, None, "chats", page, total)
    if pager:
        rows.append(pager)
    return Screen(text_key="admin_select_chat", values={"count": str(len(chats))}, rows=rows)


async def root_screen(texts: TextService, chat_id: int, chat_title: str) -> Screen:
    """Главное меню выбранного чата."""
    rows = [
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_modules"),
                callback_data=Nav(screen="modules").pack(),
                style=parse_style("blue"),
            )
        ],
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_settings"),
                callback_data=Nav(screen="settings").pack(),
                style=parse_style("blue"),
            )
        ],
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_texts"),
                callback_data=Nav(screen="texts").pack(),
                style=parse_style("blue"),
            )
        ],
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_content"),
                callback_data=Nav(screen="content").pack(),
                style=parse_style("blue"),
            )
        ],
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_chats"),
                callback_data=Nav(screen="chats").pack(),
            )
        ],
    ]
    return Screen(text_key="admin_menu", values={"chat_title": chat_title}, rows=rows)


async def modules_screen(
    texts: TextService,
    settings: SettingsService,
    registry: ModuleRegistry,
    chat_id: int,
) -> Screen:
    """Включение и выключение модулей в этом чате.

    Состояние показывается цветом кнопки: зелёная — модуль работает,
    красная — выключен.
    """
    rows: list[list[ButtonSpec]] = []
    for name in registry.disableable:
        enabled = await settings.is_module_enabled(chat_id, name)
        state_key = "admin_btn_on" if enabled else "admin_btn_off"
        rows.append(
            [
                ButtonSpec(
                    text=f"{await label(texts, chat_id, 'module_' + name)}"
                    f" — {await label(texts, chat_id, state_key)}",
                    callback_data=ModuleAction(module=name, action="toggle").pack(),
                    style=parse_style("green" if enabled else "red"),
                )
            ]
        )
    rows.append([await back_button(texts, chat_id, "root")])
    return Screen(text_key="admin_modules", rows=rows)


async def settings_modules_screen(
    texts: TextService, registry: SettingsRegistry, chat_id: int
) -> Screen:
    """Выбор раздела настроек: по одному на модуль."""
    modules = sorted({definition.module for definition in _all_defs(registry)})
    rows = [
        [
            ButtonSpec(
                text=await label(texts, chat_id, "module_" + module),
                callback_data=ModuleAction(module=module, action="open").pack(),
            )
        ]
        for module in modules
    ]
    rows.append([await back_button(texts, chat_id, "root")])
    return Screen(text_key="admin_settings", rows=rows)


async def module_settings_screen(
    texts: TextService,
    settings: SettingsService,
    registry: SettingsRegistry,
    chat_id: int,
    module: str,
) -> Screen:
    """Настройки одного модуля с текущими значениями."""
    rows: list[list[ButtonSpec]] = []
    for definition in registry.by_module(module):
        if definition.key.startswith("modules."):
            continue  # переключатель модуля живёт на своём экране
        value = await settings.get(chat_id, definition.key)
        rows.append(
            [
                ButtonSpec(
                    text=f"{definition.description}: {_show(value)}",
                    callback_data=SettingAction(
                        module=module, key=_suffix(definition.key), action="open"
                    ).pack(),
                    style=_value_style(definition, value),
                )
            ]
        )
    rows.append([await back_button(texts, chat_id, "settings")])
    return Screen(text_key="admin_module_settings",
                  values={"module": module}, rows=rows)


async def setting_screen(
    texts: TextService, chat_id: int, definition: SettingDef, value: Any
) -> Screen:
    """Экран одной настройки."""
    rows: list[list[ButtonSpec]] = []
    suffix = _suffix(definition.key)

    if definition.type is bool:
        rows.append(
            [
                ButtonSpec(
                    text=await label(texts, chat_id, "admin_btn_toggle"),
                    callback_data=SettingAction(
                        module=definition.module, key=suffix, action="toggle"
                    ).pack(),
                    style=parse_style("green" if not value else "red"),
                )
            ]
        )
    else:
        rows.append(
            [
                ButtonSpec(
                    text=await label(texts, chat_id, "admin_btn_edit"),
                    callback_data=SettingAction(
                        module=definition.module, key=suffix, action="edit"
                    ).pack(),
                    style=parse_style("blue"),
                )
            ]
        )

    rows.append(
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_reset"),
                callback_data=SettingAction(
                    module=definition.module, key=suffix, action="reset"
                ).pack(),
            ),
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_back"),
                callback_data=ModuleAction(module=definition.module, action="open").pack(),
            ),
        ]
    )

    return Screen(
        text_key="admin_setting_view",
        values={
            "setting": definition.key,
            "description": definition.description,
            "value": _show(value),
        },
        rows=rows,
    )


async def texts_modules_screen(
    texts: TextService, registry: TextRegistry, chat_id: int
) -> Screen:
    """Выбор раздела текстов."""
    modules = sorted({registry.get(key).module for key in registry.keys})
    rows = [
        [
            ButtonSpec(
                text=await label(texts, chat_id, "module_" + module),
                callback_data=TextAction(module=module, key="-", action="list").pack(),
            )
        ]
        for module in modules
    ]
    rows.append([await back_button(texts, chat_id, "root")])
    return Screen(text_key="admin_texts", rows=rows)


async def module_texts_screen(
    texts: TextService, registry: TextRegistry, chat_id: int, module: str, page: int = 0
) -> Screen:
    """Тексты одного модуля."""
    definitions = registry.by_module(module)
    visible, page, total = paginate(definitions, page)

    rows: list[list[ButtonSpec]] = []
    for definition in visible:
        source = await texts.source_of(chat_id, definition.key)
        marker = "" if source == "default" else " ✎"
        rows.append(
            [
                ButtonSpec(
                    text=f"{definition.description}{marker}",
                    callback_data=TextAction(
                        module=module, key=definition.key, action="open"
                    ).pack(),
                )
            ]
        )
    rows.append([await back_button(texts, chat_id, "texts")])
    return Screen(text_key="admin_module_texts", values={"module": module}, rows=rows)


async def text_screen(
    texts: TextService, chat_id: int, definition: TextDef, source: str
) -> Screen:
    """Экран одного текста."""
    rows = [
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_edit"),
                callback_data=TextAction(
                    module=definition.module, key=definition.key, action="edit"
                ).pack(),
                style=parse_style("blue"),
            )
        ],
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_reset"),
                callback_data=TextAction(
                    module=definition.module, key=definition.key, action="reset"
                ).pack(),
            ),
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_back"),
                callback_data=TextAction(
                    module=definition.module, key="-", action="list"
                ).pack(),
            ),
        ],
    ]
    return Screen(
        text_key="admin_text_view",
        values={
            "setting": definition.key,
            "description": definition.description,
            "source": source,
        },
        rows=rows,
    )


# ─── Вспомогательное ─────────────────────────────────────────────────────────


def _all_defs(registry: SettingsRegistry) -> list[SettingDef]:
    return [registry.get(key) for key in registry.keys]


def _suffix(key: str) -> str:
    """Часть ключа после модуля: нужна, чтобы уложиться в лимит кнопки."""
    return key.split(".", 1)[1] if "." in key else key


def _show(value: Any) -> str:
    """Значение настройки в виде, понятном человеку."""
    if isinstance(value, bool):
        return "включено" if value else "выключено"
    return str(value)


def _value_style(definition: SettingDef, value: Any):
    """Логическая настройка подсвечивается по своему состоянию."""
    if definition.type is bool:
        return parse_style("green" if value else "red")
    return None


def toggle_key(module: str) -> str:
    return module_toggle_key(module)


# ─── Разделы содержимого ─────────────────────────────────────────────────────


async def content_screen(texts: TextService, chat_id: int) -> Screen:
    """Выбор раздела: приветствие, слова, пересылки."""
    rows = [
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_welcome"),
                callback_data=WelcomeAction(action="open").pack(),
                style=parse_style("blue"),
            )
        ],
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_words"),
                callback_data=ListAction(kind="words", action="open").pack(),
                style=parse_style("blue"),
            )
        ],
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_forwards"),
                callback_data=ListAction(kind="forwards", action="open").pack(),
                style=parse_style("blue"),
            )
        ],
        [await back_button(texts, chat_id, "root")],
    ]
    return Screen(text_key="admin_content", rows=rows)


async def welcome_screen(texts: TextService, chat_id: int, configured: bool) -> Screen:
    """Экран приветствия чата."""
    rows = [
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_edit"),
                callback_data=WelcomeAction(action="set").pack(),
                style=parse_style("blue"),
            )
        ]
    ]
    if configured:
        rows.append(
            [
                ButtonSpec(
                    text=await label(texts, chat_id, "admin_btn_reset"),
                    callback_data=WelcomeAction(action="reset").pack(),
                    style=parse_style("red"),
                )
            ]
        )
    rows.append([await back_button(texts, chat_id, "content")])

    return Screen(
        text_key="admin_welcome_set" if configured else "admin_welcome_default", rows=rows
    )


async def list_screen(
    texts: TextService,
    chat_id: int,
    kind: str,
    items: list[str],
    page: int = 0,
) -> Screen:
    """Список слов или разрешённых источников с удалением по нажатию."""
    visible, page, total = paginate(items, page)
    offset = page * PAGE_SIZE

    rows: list[list[ButtonSpec]] = [
        [
            ButtonSpec(
                text=f"✕ {item}"[:BUTTON_LIMIT],
                callback_data=ListAction(
                    kind=kind, action="remove", index=offset + position
                ).pack(),
                style=parse_style("red"),
            )
        ]
        for position, item in enumerate(visible)
    ]

    rows.append(
        [
            ButtonSpec(
                text=await label(texts, chat_id, "admin_btn_add"),
                callback_data=ListAction(kind=kind, action="add").pack(),
                style=parse_style("green"),
            )
        ]
    )
    rows.append([await back_button(texts, chat_id, "content")])

    return Screen(
        text_key=f"admin_{kind}_list" if items else f"admin_{kind}_empty",
        values={"items": "\n".join(items) if items else "", "count": str(len(items))},
        rows=rows,
    )
