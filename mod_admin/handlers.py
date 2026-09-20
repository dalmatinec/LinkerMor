"""Админ-панель в личной переписке с ботом (ТЗ §3, §16).

Панель работает в личке: в группе она захламляла бы чат и была бы видна
всем участникам. Администратор нескольких чатов сначала выбирает чат, и
дальше весь диалог относится только к нему.

Права проверяются заново при каждом нажатии. Данным кнопки доверять
нельзя: нажать её может кто угодно, в том числе после того, как человека
лишили прав.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import Role
from core.errors import PermissionDenied, SettingValidationError
from core.logging import get_logger
from cache.backend import CacheBackend
from core.registry import ModuleRegistry
from guards.chat_type import InPrivate
from mod_admin import menu
from mod_admin.callbacks import (
    ChatChoice,
    ListAction,
    ModuleAction,
    Nav,
    SettingAction,
    TextAction,
    WelcomeAction,
)
from mod_admin.states import AdminPanel, ContentEdit
from mod_chats.repo import ChatRepository, MemberRepository
from sender.sender import Sender
from permissions.service import PermissionService
from settings.defs import SettingsRegistry, module_toggle_key
from settings.service import SettingsService
from texts.defs import TextRegistry
from texts.entities import EntityText
from texts.service import TextService
from ui.buttons import build_inline

log = get_logger(__name__)

router = Router(name="admin")

#: Минимальная роль для входа в панель.
PANEL_ROLE = Role.CHAT_ADMIN


async def _render(
    texts: TextService, chat_id: int | None, screen: menu.Screen
) -> tuple[EntityText, InlineKeyboardMarkup | None]:
    """Превратить экран в сообщение с клавиатурой."""
    content = await texts.render(chat_id, screen.text_key, screen.values)
    markup = build_inline(screen.rows) if screen.rows else None
    return content, markup


async def _show(
    event: Message | CallbackQuery,
    texts: TextService,
    chat_id: int | None,
    screen: menu.Screen,
) -> None:
    """Показать экран: новым сообщением или заменой текущего."""
    content, markup = await _render(texts, chat_id, screen)
    text, entities = content.to_telegram()

    if isinstance(event, CallbackQuery):
        if event.message is not None:
            await event.message.edit_text(text, entities=entities, reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, entities=entities, reply_markup=markup)


async def _selected_chat(state: FSMContext) -> int | None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    return int(chat_id) if chat_id is not None else None


async def _require_access(
    state: FSMContext, permissions: PermissionService, user_id: int
) -> int:
    """Убедиться, что человек до сих пор вправе настраивать выбранный чат.

    Проверка повторяется на каждом нажатии: права могли отобрать уже после
    того, как панель была открыта.
    """
    chat_id = await _selected_chat(state)
    if chat_id is None:
        raise PermissionDenied("Чат не выбран")

    await permissions.require_role(chat_id, user_id, PANEL_ROLE)
    return chat_id


async def _chat_title(session: AsyncSession, chat_id: int) -> str:
    chat = await ChatRepository(session).get(chat_id)
    return (chat.title if chat is not None else None) or str(chat_id)


async def _open_chat_list(
    event: Message | CallbackQuery,
    session: AsyncSession,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
    page: int = 0,
) -> None:
    """Показать чаты, доступные этому человеку."""
    user_id = event.from_user.id
    if await permissions.is_owner(user_id):
        # Владелец бота видит все подключённые чаты.
        from core.constants import ChatStatus

        chats = await ChatRepository(session).list_by_status(ChatStatus.ACTIVE, limit=200)
    else:
        chats = await MemberRepository(session).list_chats_for_user(user_id, PANEL_ROLE)

    await state.set_state(AdminPanel.browsing)
    await _show(event, texts, None, await menu.chat_list_screen(texts, chats, page))


# ─── Вход в панель ───────────────────────────────────────────────────────────


@router.message(CommandStart(), InPrivate())
@router.message(Command("admin", "panel"), InPrivate())
async def cmd_panel(
    message: Message,
    session: AsyncSession,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    """Открыть панель: сначала выбор чата."""
    await _open_chat_list(message, session, texts, permissions, state)


@router.callback_query(Nav.filter(F.screen == "chats"), InPrivate())
async def nav_chats(
    callback: CallbackQuery,
    callback_data: Nav,
    session: AsyncSession,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    await _open_chat_list(callback, session, texts, permissions, state, callback_data.page)


@router.callback_query(ChatChoice.filter(), InPrivate())
async def choose_chat(
    callback: CallbackQuery,
    callback_data: ChatChoice,
    session: AsyncSession,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    """Выбрать чат. Доступ проверяется, а не берётся из данных кнопки."""
    chat_id = callback_data.chat_id
    await permissions.require_role(chat_id, callback.from_user.id, PANEL_ROLE)

    await state.update_data(chat_id=chat_id)
    await state.set_state(AdminPanel.browsing)
    log.info("открыта панель чата", extra={"chat_id": chat_id, "actor": callback.from_user.id})

    await _show(
        callback, texts, chat_id,
        await menu.root_screen(texts, chat_id, await _chat_title(session, chat_id)),
    )


@router.callback_query(Nav.filter(F.screen == "root"), InPrivate())
async def nav_root(
    callback: CallbackQuery,
    session: AsyncSession,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    await state.set_state(AdminPanel.browsing)
    await _show(
        callback, texts, chat_id,
        await menu.root_screen(texts, chat_id, await _chat_title(session, chat_id)),
    )


# ─── Модули ──────────────────────────────────────────────────────────────────


@router.callback_query(Nav.filter(F.screen == "modules"), InPrivate())
async def nav_modules(
    callback: CallbackQuery,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    registry: ModuleRegistry,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    await _show(
        callback, texts, chat_id,
        await menu.modules_screen(texts, settings, registry, chat_id),
    )


@router.callback_query(ModuleAction.filter(F.action == "toggle"), InPrivate())
async def toggle_module(
    callback: CallbackQuery,
    callback_data: ModuleAction,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    registry: ModuleRegistry,
    state: FSMContext,
) -> None:
    """Включить или выключить модуль в этом чате."""
    chat_id = await _require_access(state, permissions, callback.from_user.id)

    key = module_toggle_key(callback_data.module)
    current = await settings.get(chat_id, key)
    await settings.set(chat_id, key, not current, callback.from_user.id)

    await _show(
        callback, texts, chat_id,
        await menu.modules_screen(texts, settings, registry, chat_id),
    )


# ─── Настройки ───────────────────────────────────────────────────────────────


@router.callback_query(Nav.filter(F.screen == "settings"), InPrivate())
async def nav_settings(
    callback: CallbackQuery,
    texts: TextService,
    permissions: PermissionService,
    settings_registry: SettingsRegistry,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    await _show(
        callback, texts, chat_id,
        await menu.settings_modules_screen(texts, settings_registry, chat_id),
    )


@router.callback_query(ModuleAction.filter(F.action == "open"), InPrivate())
async def open_module_settings(
    callback: CallbackQuery,
    callback_data: ModuleAction,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    settings_registry: SettingsRegistry,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    await _show(
        callback, texts, chat_id,
        await menu.module_settings_screen(
            texts, settings, settings_registry, chat_id, callback_data.module
        ),
    )


def _full_key(callback_data: SettingAction) -> str:
    return f"{callback_data.module}.{callback_data.key}"


@router.callback_query(SettingAction.filter(F.action == "open"), InPrivate())
async def open_setting(
    callback: CallbackQuery,
    callback_data: SettingAction,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    settings_registry: SettingsRegistry,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    definition = settings_registry.get(_full_key(callback_data))
    value = await settings.get(chat_id, definition.key)

    await _show(callback, texts, chat_id, await menu.setting_screen(texts, chat_id, definition, value))


@router.callback_query(SettingAction.filter(F.action == "toggle"), InPrivate())
async def toggle_setting(
    callback: CallbackQuery,
    callback_data: SettingAction,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    settings_registry: SettingsRegistry,
    state: FSMContext,
) -> None:
    """Переключить логическую настройку."""
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    definition = settings_registry.get(_full_key(callback_data))

    current = await settings.get(chat_id, definition.key)
    value = await settings.set(chat_id, definition.key, not current, callback.from_user.id)

    await _show(callback, texts, chat_id, await menu.setting_screen(texts, chat_id, definition, value))


@router.callback_query(SettingAction.filter(F.action == "reset"), InPrivate())
async def reset_setting(
    callback: CallbackQuery,
    callback_data: SettingAction,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    settings_registry: SettingsRegistry,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    definition = settings_registry.get(_full_key(callback_data))
    value = await settings.reset(chat_id, definition.key, callback.from_user.id)

    await _show(callback, texts, chat_id, await menu.setting_screen(texts, chat_id, definition, value))


@router.callback_query(SettingAction.filter(F.action == "edit"), InPrivate())
async def edit_setting(
    callback: CallbackQuery,
    callback_data: SettingAction,
    texts: TextService,
    permissions: PermissionService,
    settings_registry: SettingsRegistry,
    state: FSMContext,
) -> None:
    """Попросить новое значение настройки."""
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    definition = settings_registry.get(_full_key(callback_data))

    await state.update_data(pending_setting=definition.key)
    await state.set_state(AdminPanel.awaiting_setting_value)

    await _show(
        callback, texts, chat_id,
        menu.Screen(
            text_key="admin_setting_prompt",
            values={"setting": definition.key, "description": definition.description},
        ),
    )


@router.message(AdminPanel.awaiting_setting_value, InPrivate(), F.text)
async def receive_setting_value(
    message: Message,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    settings_registry: SettingsRegistry,
    state: FSMContext,
) -> None:
    """Принять новое значение настройки."""
    chat_id = await _require_access(state, permissions, message.from_user.id)
    data = await state.get_data()
    definition = settings_registry.get(data["pending_setting"])

    try:
        value = await settings.set(chat_id, definition.key, message.text, message.from_user.id)
    except SettingValidationError as exc:
        await _show(
            message, texts, chat_id,
            menu.Screen(text_key="admin_setting_invalid", values={"reason": str(exc)}),
        )
        return

    await state.set_state(AdminPanel.browsing)
    await _show(message, texts, chat_id, await menu.setting_screen(texts, chat_id, definition, value))


# ─── Тексты ──────────────────────────────────────────────────────────────────


@router.callback_query(Nav.filter(F.screen == "texts"), InPrivate())
async def nav_texts(
    callback: CallbackQuery,
    texts: TextService,
    permissions: PermissionService,
    text_registry: TextRegistry,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    await _show(
        callback, texts, chat_id,
        await menu.texts_modules_screen(texts, text_registry, chat_id),
    )


@router.callback_query(TextAction.filter(F.action == "list"), InPrivate())
async def list_module_texts(
    callback: CallbackQuery,
    callback_data: TextAction,
    texts: TextService,
    permissions: PermissionService,
    text_registry: TextRegistry,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    await _show(
        callback, texts, chat_id,
        await menu.module_texts_screen(texts, text_registry, chat_id, callback_data.module),
    )


@router.callback_query(TextAction.filter(F.action == "open"), InPrivate())
async def open_text(
    callback: CallbackQuery,
    callback_data: TextAction,
    texts: TextService,
    permissions: PermissionService,
    text_registry: TextRegistry,
    state: FSMContext,
) -> None:
    """Показать текст и то, откуда он взят."""
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    definition = text_registry.get(callback_data.key)
    source = await texts.source_of(chat_id, definition.key)

    await _show(callback, texts, chat_id, await menu.text_screen(texts, chat_id, definition, source))

    # Сам текст показывается отдельным сообщением: так видно форматирование
    # и премиум-эмодзи ровно такими, какими их увидят участники чата.
    current = await texts.get(chat_id, definition.key)
    preview, entities = current.to_telegram()
    if callback.message is not None:
        await callback.message.answer(preview, entities=entities)


@router.callback_query(TextAction.filter(F.action == "edit"), InPrivate())
async def edit_text(
    callback: CallbackQuery,
    callback_data: TextAction,
    texts: TextService,
    permissions: PermissionService,
    text_registry: TextRegistry,
    state: FSMContext,
) -> None:
    """Попросить новый текст."""
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    definition = text_registry.get(callback_data.key)

    await state.update_data(pending_text=definition.key)
    await state.set_state(AdminPanel.awaiting_text)

    await _show(
        callback, texts, chat_id,
        menu.Screen(
            text_key="admin_text_prompt",
            values={"setting": definition.key, "description": definition.description},
        ),
    )


@router.callback_query(TextAction.filter(F.action == "reset"), InPrivate())
async def reset_text(
    callback: CallbackQuery,
    callback_data: TextAction,
    texts: TextService,
    permissions: PermissionService,
    text_registry: TextRegistry,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    definition = text_registry.get(callback_data.key)
    await texts.reset_for_chat(chat_id, definition.key)
    source = await texts.source_of(chat_id, definition.key)

    await _show(callback, texts, chat_id, await menu.text_screen(texts, chat_id, definition, source))


@router.message(AdminPanel.awaiting_text, InPrivate(), F.text | F.caption)
async def receive_text(
    message: Message,
    texts: TextService,
    permissions: PermissionService,
    text_registry: TextRegistry,
    state: FSMContext,
) -> None:
    """Принять новый текст вместе с форматированием.

    Сохраняются entity исходного сообщения, поэтому жирный шрифт, ссылки и
    премиум-эмодзи переносятся ровно такими, какими их отправил
    администратор.
    """
    chat_id = await _require_access(state, permissions, message.from_user.id)
    data = await state.get_data()
    definition = text_registry.get(data["pending_text"])

    value = EntityText.from_telegram(
        message.text or message.caption, message.entities or message.caption_entities
    )

    try:
        await texts.set_for_chat(chat_id, definition.key, value, message.from_user.id)
    except SettingValidationError as exc:
        await _show(
            message, texts, chat_id,
            menu.Screen(text_key="admin_text_invalid", values={"reason": str(exc)}),
        )
        return

    await state.set_state(AdminPanel.browsing)
    source = await texts.source_of(chat_id, definition.key)
    await _show(message, texts, chat_id, await menu.text_screen(texts, chat_id, definition, source))


@router.message(Command("cancel"), InPrivate())
async def cancel(
    message: Message, texts: TextService, state: FSMContext, **_: Any
) -> None:
    """Прервать ввод значения."""
    chat_id = await _selected_chat(state)
    await state.set_state(AdminPanel.browsing)
    await _show(message, texts, chat_id, menu.Screen(text_key="admin_cancelled"))


# ─── Содержимое чата: приветствие, слова, пересылки ──────────────────────────


async def _words_of(session: AsyncSession, chat_id: int) -> list[str]:
    from mod_antispam.repo import WordRepository

    return sorted(await WordRepository(session).list_words(chat_id))


async def _forwards_of(session: AsyncSession, chat_id: int) -> list:
    from mod_antispam.repo import ForwardRepository

    return await ForwardRepository(session).list_all(chat_id)


def _forward_labels(sources: list) -> list[str]:
    return [f"{item.title or item.source_id}" for item in sources]


async def _drop_list_cache(cache: CacheBackend, chat_id: int, kind: str) -> None:
    from cache.keys import ChatEntity, chat_key

    await cache.delete(chat_key(ChatEntity.FILTER_RULES, chat_id, kind))


@router.callback_query(Nav.filter(F.screen == "content"), InPrivate())
async def nav_content(
    callback: CallbackQuery,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    await _show(callback, texts, chat_id, await menu.content_screen(texts, chat_id))


@router.callback_query(WelcomeAction.filter(F.action == "open"), InPrivate())
async def open_welcome(
    callback: CallbackQuery,
    session: AsyncSession,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    sender: Sender,
    state: FSMContext,
) -> None:
    """Показать приветствие выбранного чата."""
    chat_id = await _require_access(state, permissions, callback.from_user.id)

    from mod_welcome.service import WelcomeService

    welcome = await WelcomeService(session, settings, texts, sender).get(chat_id)
    await _show(callback, texts, chat_id, await menu.welcome_screen(texts, chat_id,
                                                                    welcome is not None))

    # Приветствие показывается отдельным сообщением ровно таким, каким его
    # увидят новички — с оформлением и вложением.
    if welcome is not None and callback.message is not None:
        body = EntityText.from_storage(welcome.content.text or "", welcome.content.entities)
        preview, entities = body.to_telegram()
        if preview:
            await callback.message.answer(preview, entities=entities)


@router.callback_query(WelcomeAction.filter(F.action == "set"), InPrivate())
async def ask_welcome(
    callback: CallbackQuery,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)
    await state.set_state(ContentEdit.awaiting_welcome)
    await _show(callback, texts, chat_id, menu.Screen(text_key="admin_welcome_prompt"))


@router.message(ContentEdit.awaiting_welcome, InPrivate())
async def receive_welcome(
    message: Message,
    session: AsyncSession,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    sender: Sender,
    state: FSMContext,
) -> None:
    """Принять сообщение, которое станет приветствием чата."""
    chat_id = await _require_access(state, permissions, message.from_user.id)

    from mod_triggers.content import UnsupportedContent
    from mod_welcome.service import WelcomeService

    try:
        await WelcomeService(session, settings, texts, sender).set_from_message(
            chat_id, message, message.from_user.id
        )
    except UnsupportedContent as exc:
        await _show(
            message, texts, chat_id,
            menu.Screen(text_key="admin_welcome_invalid", values={"reason": str(exc)}),
        )
        return

    await state.set_state(AdminPanel.browsing)
    await _show(message, texts, chat_id, await menu.welcome_screen(texts, chat_id, True))


@router.callback_query(WelcomeAction.filter(F.action == "reset"), InPrivate())
async def reset_welcome(
    callback: CallbackQuery,
    session: AsyncSession,
    texts: TextService,
    settings: SettingsService,
    permissions: PermissionService,
    sender: Sender,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)

    from mod_welcome.service import WelcomeService

    await WelcomeService(session, settings, texts, sender).clear(chat_id)
    await _show(callback, texts, chat_id, await menu.welcome_screen(texts, chat_id, False))


@router.callback_query(ListAction.filter(F.action == "open"), InPrivate())
async def open_list(
    callback: CallbackQuery,
    callback_data: ListAction,
    session: AsyncSession,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    """Показать список слов или разрешённых источников."""
    chat_id = await _require_access(state, permissions, callback.from_user.id)

    items = (
        await _words_of(session, chat_id)
        if callback_data.kind == "words"
        else _forward_labels(await _forwards_of(session, chat_id))
    )
    await _show(callback, texts, chat_id,
                await menu.list_screen(texts, chat_id, callback_data.kind, items))


@router.callback_query(ListAction.filter(F.action == "add"), InPrivate())
async def ask_list_item(
    callback: CallbackQuery,
    callback_data: ListAction,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    chat_id = await _require_access(state, permissions, callback.from_user.id)

    if callback_data.kind == "words":
        await state.set_state(ContentEdit.awaiting_word)
        key = "admin_word_prompt"
    else:
        await state.set_state(ContentEdit.awaiting_forward)
        key = "admin_forward_prompt"

    await _show(callback, texts, chat_id, menu.Screen(text_key=key))


@router.callback_query(ListAction.filter(F.action == "remove"), InPrivate())
async def remove_list_item(
    callback: CallbackQuery,
    callback_data: ListAction,
    session: AsyncSession,
    cache: CacheBackend,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    """Убрать элемент списка по его номеру."""
    chat_id = await _require_access(state, permissions, callback.from_user.id)

    if callback_data.kind == "words":
        from mod_antispam.repo import WordRepository

        words = await _words_of(session, chat_id)
        if 0 <= callback_data.index < len(words):
            await WordRepository(session).remove(chat_id, words[callback_data.index])
            await _drop_list_cache(cache, chat_id, "words")
        items = await _words_of(session, chat_id)
    else:
        from mod_antispam.repo import ForwardRepository

        sources = await _forwards_of(session, chat_id)
        if 0 <= callback_data.index < len(sources):
            await ForwardRepository(session).deny(
                chat_id, sources[callback_data.index].source_id
            )
            await _drop_list_cache(cache, chat_id, "forwards")
        items = _forward_labels(await _forwards_of(session, chat_id))

    await _show(callback, texts, chat_id,
                await menu.list_screen(texts, chat_id, callback_data.kind, items))


@router.message(ContentEdit.awaiting_word, InPrivate(), F.text)
async def receive_word(
    message: Message,
    session: AsyncSession,
    cache: CacheBackend,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    """Добавить запрещённое слово. Можно прислать несколько строками."""
    chat_id = await _require_access(state, permissions, message.from_user.id)

    from mod_antispam.repo import WordRepository

    repo = WordRepository(session)
    for line in (message.text or "").splitlines():
        word = line.strip().lower()
        if word:
            await repo.add(chat_id, word, message.from_user.id)

    await _drop_list_cache(cache, chat_id, "words")
    await state.set_state(AdminPanel.browsing)
    await _show(message, texts, chat_id,
                await menu.list_screen(texts, chat_id, "words", await _words_of(session, chat_id)))


@router.message(ContentEdit.awaiting_forward, InPrivate())
async def receive_forward(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    cache: CacheBackend,
    texts: TextService,
    permissions: PermissionService,
    state: FSMContext,
) -> None:
    """Разрешить источник пересылок.

    Принимается тремя способами: пересланное сюда сообщение, ``@username``
    канала или числовой идентификатор. Пересылка — самый надёжный: у
    закрытых каналов публичного имени нет.
    """
    chat_id = await _require_access(state, permissions, message.from_user.id)

    from mod_antispam.models import ForwardSource
    from mod_antispam.repo import ForwardRepository
    from mod_antispam.rule_forwards import origin_of

    source_type: str | None = None
    source_id: int | None = None
    title = ""

    origin = origin_of(message)
    if origin is not None and origin[1]:
        source_type, source_id, title = origin
    else:
        token = (message.text or "").strip()
        if token.lstrip("-").isdigit():
            source_type, source_id, title = ForwardSource.CHANNEL, int(token), token
        elif token.startswith("@"):
            try:
                found = await bot.get_chat(token)
                source_type = ForwardSource.CHANNEL
                source_id = found.id
                title = found.title or token
            except TelegramAPIError:
                source_id = None

    if source_id is None or source_type is None:
        await _show(message, texts, chat_id,
                    menu.Screen(text_key="admin_forward_unknown"))
        return

    await ForwardRepository(session).allow(
        chat_id, source_type, source_id, title, message.from_user.id
    )
    await _drop_list_cache(cache, chat_id, "forwards")
    await state.set_state(AdminPanel.browsing)

    items = _forward_labels(await _forwards_of(session, chat_id))
    await _show(message, texts, chat_id,
                await menu.list_screen(texts, chat_id, "forwards", items))
