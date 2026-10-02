"""Админка в личке бота: всё настраивается кнопками."""

from __future__ import annotations

import time
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    Message,
    MessageOriginUser,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot import relay, stored
from bot.broadcast import STOP_KB, Broadcaster
from bot.db import Database
from bot.filters import is_admin, is_owner
from bot.settings import LIMITS, Settings

router = Router(name="admin")
router.message.filter(is_admin)
router.callback_query.filter(is_admin)


class Panel(StatesGroup):
    welcome = State()
    ad = State()
    broadcast = State()
    group = State()
    ban_id = State()
    admin_id = State()


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


BACK = [btn("« Назад", "a:main")]
CANCEL_KB = kb([btn("✖️ Отмена", "a:main")])
ON = {True: "✅ вкл", False: "⛔ выкл"}
FLOOD_STEPS = {"flood_limit": 1, "flood_window": 5, "flood_mute": 10}
SEND_ANY = (
    "Пришлите сообщение: текст, фото, видео, GIF, файл, голосовое, кружок "
    "или стикер. Жирный, курсив, подчёркнутый, спойлеры, ссылки и "
    "премиум-эмодзи сохранятся как есть.\n\n/cancel — отмена"
)


async def show(target: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Обновить панель на месте, а если нельзя — прислать заново."""
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            await target.answer()
            return
        except TelegramBadRequest:
            await target.answer()
            target = target.message
    await target.answer(text, parse_mode="HTML", reply_markup=markup)


def group_name(settings: Settings) -> str:
    if settings.group_id is None:
        return "не выбрана"
    title = escape(settings["group_title"] or "без названия")
    return f"{title} (<code>{settings.group_id}</code>)"


# ---- главное меню -----------------------------------------------------------

def main_view(settings: Settings, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "⚙️ <b>Админка</b>\n\n"
        f"👥 Рабочая группа: {group_name(settings)}\n"
        f"🧩 Капча: {ON[settings['captcha']]}\n"
        f"🛡 Антифлуд: {settings['flood_limit']} сообщ. за {settings['flood_window']} сек. "
        f"→ пауза {settings['flood_mute']} сек.\n"
        f"👋 Приветствие: {escape(stored.describe(settings['welcome']))}\n"
        f"📢 Реклама при старте: {ON[settings['start_ad_on']]}"
    )
    rows = [
        [btn("👋 Приветствие", "a:wel"), btn("📢 Реклама при старте", "a:ad")],
        [btn("📨 Рассылка", "a:bc"), btn("👥 Рабочая группа", "a:grp")],
        [btn(f"🧩 Капча: {ON[settings['captcha']]}", "a:cap"), btn("🛡 Антифлуд", "a:fl")],
        [btn("🚫 Баны", "a:ban"), btn("📊 Статистика", "a:st")],
    ]
    if settings.is_owner(user_id):
        rows.append([btn("👮 Админы", "a:adm")])
    rows.append([btn("✖️ Закрыть", "a:close")])
    return text, kb(*rows)


@router.message(Command("admin", "panel"), F.chat.type == "private")
async def open_panel(message: Message, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await show(message, *main_view(settings, message.from_user.id))


@router.message(Command("cancel"), F.chat.type == "private")
async def cancel(message: Message, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
    await show(message, *main_view(settings, message.from_user.id))


@router.callback_query(F.data == "a:main")
async def to_main(call: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await show(call, *main_view(settings, call.from_user.id))


@router.callback_query(F.data == "a:close")
async def close(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.delete()
    await call.answer()


# ---- приветствие и реклама ---------------------------------------------------

def stored_view(settings: Settings, kind: str) -> tuple[str, InlineKeyboardMarkup]:
    if kind == "wel":
        value = settings["welcome"]
        text = (
            "👋 <b>Приветствие</b>\n\n"
            "Приходит после /start (и после капчи, если она включена).\n\n"
            f"Сейчас: {escape(stored.describe(value)) if value else 'стандартное'}"
        )
        rows = [
            [btn("✏️ Задать новое", "a:wel:set"), btn("👁 Посмотреть", "a:wel:show")],
            [btn("♻️ Вернуть стандартное", "a:wel:del")],
            BACK,
        ]
    else:
        value = settings["start_ad"]
        text = (
            "📢 <b>Реклама при старте</b>\n\n"
            "Приходит сразу после приветствия, один раз на каждый /start.\n\n"
            f"Сейчас: {escape(stored.describe(value))}\n"
            f"Показ: {ON[settings['start_ad_on']]}"
        )
        rows = [
            [btn("✏️ Задать", "a:ad:set"), btn("👁 Посмотреть", "a:ad:show")],
            [btn("⛔ Выключить" if settings["start_ad_on"] else "✅ Включить", "a:ad:toggle"),
             btn("🗑 Удалить", "a:ad:del")],
            BACK,
        ]
    return text, kb(*rows)


KEYS = {"wel": "welcome", "ad": "start_ad"}


@router.callback_query(F.data.in_({"a:wel", "a:ad"}))
async def stored_menu(call: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await show(call, *stored_view(settings, call.data[2:]))


@router.callback_query(F.data.in_({"a:wel:set", "a:ad:set"}))
async def stored_ask(call: CallbackQuery, state: FSMContext) -> None:
    kind = call.data.split(":")[1]
    await state.set_state(Panel.welcome if kind == "wel" else Panel.ad)
    title = "новое приветствие" if kind == "wel" else "рекламное сообщение"
    await show(call, f"✏️ <b>Пришлите {title}</b>\n\n{SEND_ANY}", CANCEL_KB)


@router.message(StateFilter(Panel.welcome, Panel.ad), F.chat.type == "private")
async def stored_save(message: Message, settings: Settings, state: FSMContext) -> None:
    kind = "wel" if await state.get_state() == Panel.welcome.state else "ad"
    try:
        value = stored.from_message(message)
    except stored.UnsupportedMessage:
        await message.answer("Такой тип сообщения не подходит. Пришлите другое или /cancel.")
        return
    await settings.set(KEYS[kind], value)
    if kind == "ad":
        await settings.set("start_ad_on", True)
    await state.clear()
    await message.answer("✅ Сохранено.")
    await show(message, *stored_view(settings, kind))


@router.callback_query(F.data.in_({"a:wel:show", "a:ad:show"}))
async def stored_preview(call: CallbackQuery, bot: Bot, settings: Settings) -> None:
    kind = call.data.split(":")[1]
    if kind == "wel":
        await relay.send_welcome(bot, settings, call.from_user.id)
    elif settings["start_ad"]:
        await stored.send(bot, call.from_user.id, settings["start_ad"])
    else:
        await call.answer("Реклама не задана", show_alert=True)
        return
    await call.answer()
    await show(call.message, *stored_view(settings, kind))


@router.callback_query(F.data.in_({"a:wel:del", "a:ad:del"}))
async def stored_delete(call: CallbackQuery, settings: Settings) -> None:
    kind = call.data.split(":")[1]
    await settings.set(KEYS[kind], None)
    if kind == "ad":
        await settings.set("start_ad_on", False)
    await show(call, *stored_view(settings, kind))


@router.callback_query(F.data == "a:ad:toggle")
async def ad_toggle(call: CallbackQuery, settings: Settings) -> None:
    if not settings["start_ad"] and not settings["start_ad_on"]:
        await call.answer("Сначала задайте рекламное сообщение", show_alert=True)
        return
    await settings.set("start_ad_on", not settings["start_ad_on"])
    await show(call, *stored_view(settings, "ad"))


# ---- рабочая группа ----------------------------------------------------------

def group_view(settings: Settings) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "👥 <b>Рабочая группа</b>\n\n"
        f"Сейчас: {group_name(settings)}\n\n"
        "Сюда приходят /start и сообщения пользователей. Ответить "
        "пользователю — ответить (reply) на его сообщение; отвечать могут "
        "все участники группы.\n\n"
        "Сменить группу: добавьте бота в новую группу и нажмите "
        "«Выбрать группу» — или напишите <code>/setgroup</code> в самой группе."
    )
    rows = [[btn("📌 Выбрать группу", "a:grp:pick")]]
    if settings.group_id is not None:
        rows.append([btn("🧪 Проверить связь", "a:grp:test")])
    rows.append(BACK)
    return text, kb(*rows)


@router.callback_query(F.data == "a:grp")
async def group_menu(call: CallbackQuery, settings: Settings) -> None:
    await show(call, *group_view(settings))


@router.callback_query(F.data == "a:grp:pick")
async def group_pick(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Panel.group)
    picker = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="📌 Выбрать группу",
                request_chat=KeyboardButtonRequestChat(
                    request_id=1, chat_is_channel=False, bot_is_member=True, request_title=True,
                ),
            )],
            [KeyboardButton(text="✖️ Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await call.answer()
    await call.message.answer(
        "Нажмите кнопку внизу и выберите группу. В списке только группы, "
        "где уже есть бот.",
        reply_markup=picker,
    )


@router.message(Panel.group, F.chat_shared)
async def group_chosen(message: Message, bot: Bot, settings: Settings, state: FSMContext) -> None:
    shared = message.chat_shared
    await state.clear()
    await _bind_group(message, bot, settings, shared.chat_id, shared.title)


@router.message(Panel.group)
async def group_pick_cancel(message: Message, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
    await show(message, *group_view(settings))


async def _bind_group(
    reply_to: Message, bot: Bot, settings: Settings, chat_id: int, title: str | None
) -> None:
    try:
        await bot.send_message(chat_id, "✅ Эта группа теперь рабочая: сюда будут приходить обращения.")
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await reply_to.answer(
            f"❌ Бот не может писать в эту группу: {escape(exc.message)}",
            parse_mode="HTML", reply_markup=ReplyKeyboardRemove(),
        )
        return
    await settings.set("group_id", chat_id)
    await settings.set("group_title", title)
    await reply_to.answer("✅ Рабочая группа выбрана.", reply_markup=ReplyKeyboardRemove())
    if reply_to.chat.type == "private":
        await show(reply_to, *group_view(settings))


@router.message(Command("setgroup"), F.chat.type.in_({"group", "supergroup"}))
async def set_group_here(message: Message, bot: Bot, settings: Settings) -> None:
    await _bind_group(message, bot, settings, message.chat.id, message.chat.title)


@router.callback_query(F.data == "a:grp:test")
async def group_test(call: CallbackQuery, bot: Bot, settings: Settings) -> None:
    try:
        await bot.send_message(settings.group_id, "🧪 Проверка связи: бот на месте.")
        await call.answer("✅ Сообщение в группу отправлено", show_alert=True)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await call.answer(f"❌ {exc.message}"[:200], show_alert=True)


# ---- капча и антифлуд --------------------------------------------------------

@router.callback_query(F.data == "a:cap")
async def captcha_toggle(call: CallbackQuery, settings: Settings) -> None:
    await settings.set("captcha", not settings["captcha"])
    await show(call, *main_view(settings, call.from_user.id))


def flood_view(settings: Settings) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🛡 <b>Антифлуд</b>\n\n"
        f"Если пользователь пишет больше <b>{settings['flood_limit']}</b> сообщений "
        f"за <b>{settings['flood_window']}</b> сек., бот перестаёт пересылать его "
        f"сообщения на <b>{settings['flood_mute']}</b> сек. и предупреждает его "
        "и рабочую группу. Альбом считается одним сообщением.\n\n"
        "Исходящие сообщения бот сам держит в лимитах Telegram — это не настраивается."
    )
    rows = []
    for key, label, unit in (
        ("flood_limit", "Сообщений", ""),
        ("flood_window", "За", " сек."),
        ("flood_mute", "Пауза", " сек."),
    ):
        step = FLOOD_STEPS[key]
        rows.append([
            btn("−", f"a:fl:{key}:-{step}"),
            btn(f"{label}: {settings[key]}{unit}", "a:fl"),
            btn("+", f"a:fl:{key}:{step}"),
        ])
    rows.append(BACK)
    return text, kb(*rows)


@router.callback_query(F.data == "a:fl")
async def flood_menu(call: CallbackQuery, settings: Settings) -> None:
    await show(call, *flood_view(settings))


@router.callback_query(F.data.startswith("a:fl:"))
async def flood_change(call: CallbackQuery, settings: Settings) -> None:
    _, _, key, delta = call.data.split(":")
    if key not in LIMITS:
        await call.answer()
        return
    await settings.set(key, settings[key] + int(delta))
    await show(call, *flood_view(settings))


# ---- баны -------------------------------------------------------------------

async def bans_view(db: Database) -> tuple[str, InlineKeyboardMarkup]:
    banned = await db.banned_users(limit=30)
    lines = ["🚫 <b>Баны</b>", ""]
    if not banned:
        lines.append("Забаненных нет.")
    rows = []
    for u in banned:
        reason = f" — {escape(u.ban_reason)}" if u.ban_reason else ""
        lines.append(f"• {escape(u.full_name)} <code>{u.id}</code>{reason}")
        rows.append([btn(f"✅ Разбанить {u.full_name[:20]} · {u.id}", f"a:unb:{u.id}")])
    lines += [
        "",
        "Узнать ID: в рабочей группе кнопка 👤 под сообщением пользователя или "
        "<code>/id</code> ответом на его сообщение.\n"
        "Команды: <code>/ban ID причина</code>, <code>/unban ID</code> — "
        "в группе и здесь.",
    ]
    rows += [[btn("➕ Забанить по ID", "a:ban:add")], BACK]
    return "\n".join(lines), kb(*rows)


@router.callback_query(F.data == "a:ban")
async def bans_menu(call: CallbackQuery, db: Database) -> None:
    await show(call, *await bans_view(db))


@router.callback_query(F.data.regexp(r"^a:unb:-?\d+$"))
async def bans_unban(call: CallbackQuery, db: Database) -> None:
    await db.set_banned(int(call.data.split(":")[2]), False)
    await show(call, *await bans_view(db))


@router.callback_query(F.data == "a:ban:add")
async def bans_ask(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Panel.ban_id)
    await show(call, "Пришлите ID пользователя и, по желанию, причину:\n<code>123456789 спам</code>", CANCEL_KB)


@router.message(Panel.ban_id, F.text)
async def bans_add(message: Message, db: Database, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if not parts or not parts[0].lstrip("-").isdigit():
        await message.answer("Нужен числовой ID. Попробуйте ещё раз или /cancel.")
        return
    await db.set_banned(int(parts[0]), True, parts[1] if len(parts) > 1 else None)
    await state.clear()
    await show(message, *await bans_view(db))


@router.message(Panel.ban_id)
async def bans_add_not_text(message: Message) -> None:
    await message.answer("Нужен числовой ID текстом. Попробуйте ещё раз или /cancel.")


# ---- статистика --------------------------------------------------------------

@router.callback_query(F.data == "a:st")
async def stats(call: CallbackQuery, db: Database) -> None:
    s = await db.stats()
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Пользователей: {s['total']}\n"
        f"Прошли капчу: {s['passed']}\n"
        f"Активны за сутки: {s['day']}\n"
        f"Активны за неделю: {s['week']}\n"
        f"Остановили бота: {s['blocked']}\n"
        f"Забанены: {s['banned']}\n"
        f"Сообщений в группу: {s['messages']}"
    )
    await show(call, text, kb([btn("🔄 Обновить", "a:st")], BACK))


# ---- админы (только владелец) ------------------------------------------------

def admins_view(settings: Settings) -> tuple[str, InlineKeyboardMarkup]:
    owners = ", ".join(f"<code>{i}</code>" for i in sorted(settings.owner_ids))
    lines = ["👮 <b>Админы</b>", "", f"Владельцы (из .env): {owners}", ""]
    rows = []
    admins = sorted(settings.admins - set(settings.owner_ids))
    if not admins:
        lines.append("Других админов нет.")
    for a in admins:
        lines.append(f"• <code>{a}</code>")
        rows.append([btn(f"🗑 Снять {a}", f"a:adm:del:{a}")])
    lines.append("\nАдмины могут всё, кроме управления админами.")
    rows += [[btn("➕ Добавить", "a:adm:add")], BACK]
    return "\n".join(lines), kb(*rows)


@router.callback_query(F.data == "a:adm", is_owner)
async def admins_menu(call: CallbackQuery, settings: Settings) -> None:
    await show(call, *admins_view(settings))


@router.callback_query(F.data.regexp(r"^a:adm:del:\d+$"), is_owner)
async def admins_remove(call: CallbackQuery, settings: Settings) -> None:
    await settings.remove_admin(int(call.data.split(":")[3]))
    await show(call, *admins_view(settings))


@router.callback_query(F.data == "a:adm:add", is_owner)
async def admins_ask(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Panel.admin_id)
    await show(call, "Пришлите ID нового админа или перешлите любое его сообщение.", CANCEL_KB)


@router.message(Panel.admin_id, is_owner)
async def admins_add(message: Message, settings: Settings, state: FSMContext) -> None:
    new_id = None
    if isinstance(message.forward_origin, MessageOriginUser):
        new_id = message.forward_origin.sender_user.id
    elif message.text and message.text.strip().isdigit():
        new_id = int(message.text.strip())
    if new_id is None:
        await message.answer(
            "Не вижу ID. Если пересылка скрыта настройками приватности — "
            "пришлите ID числом. /cancel — отмена."
        )
        return
    await settings.add_admin(new_id, message.from_user.id)
    await state.clear()
    await show(message, *admins_view(settings))


@router.callback_query(F.data.startswith("a:adm"))
async def admins_denied(call: CallbackQuery) -> None:
    await call.answer("Только для владельца", show_alert=True)


# ---- рассылка ----------------------------------------------------------------

AUDIENCES = {"0": ("всем", None), "30": ("активным за 30 дней", 30), "7": ("активным за 7 дней", 7)}


def _ago(ts: int) -> str:
    if not ts:
        return "ещё не было"
    minutes = int((time.time() - ts) // 60)
    if minutes < 60:
        return f"{minutes} мин. назад"
    if minutes < 48 * 60:
        return f"{minutes // 60} ч. назад"
    return f"{minutes // 1440} дн. назад"


@router.callback_query(F.data == "a:bc")
async def bc_ask(
    call: CallbackQuery, settings: Settings, state: FSMContext, broadcaster: Broadcaster
) -> None:
    if broadcaster.running:
        await call.answer("Рассылка уже идёт", show_alert=True)
        return
    await state.set_state(Panel.broadcast)
    await show(
        call,
        "📨 <b>Рассылка</b>\n\n"
        f"Последняя рассылка: {_ago(settings['last_broadcast'])}.\n"
        "Получат только те, кто прошёл капчу, не забанен и не остановил бота. "
        "Рассылка идёт медленнее обычных сообщений, чтобы ответы поддержки "
        f"не задерживались.\n\n{SEND_ANY}",
        CANCEL_KB,
    )


@router.message(Panel.broadcast, F.chat.type == "private")
async def bc_preview(message: Message, bot: Bot, db: Database, state: FSMContext) -> None:
    try:
        value = stored.from_message(message)
    except stored.UnsupportedMessage:
        await message.answer("Такой тип сообщения не подходит. Пришлите другое или /cancel.")
        return
    await state.update_data(bc=value)
    await message.answer("👁 Так увидят пользователи:")
    await stored.send(bot, message.chat.id, value)
    rows = []
    for key, (label, days) in AUDIENCES.items():
        count = len(await db.audience(days))
        rows.append([btn(f"Отправить {label} ({count})", f"a:bc:aud:{key}")])
    rows.append([btn("✖️ Отмена", "a:main")])
    await message.answer("Кому отправить?", reply_markup=kb(*rows))


@router.callback_query(Panel.broadcast, F.data.startswith("a:bc:aud:"))
async def bc_confirm(call: CallbackQuery, db: Database, settings: Settings, state: FSMContext) -> None:
    key = call.data.rsplit(":", 1)[1]
    label, days = AUDIENCES[key]
    count = len(await db.audience(days))
    warn = ""
    if settings["last_broadcast"] and time.time() - settings["last_broadcast"] < 86400:
        warn = (
            f"\n\n⚠️ Предыдущая рассылка была {_ago(settings['last_broadcast'])}. "
            "Частые рассылки раздражают — люди останавливают бота."
        )
    await show(
        call,
        f"Отправить {label}: <b>{count}</b> получателей?{warn}",
        kb([btn("✅ Отправить", f"a:bc:go:{key}")], [btn("✖️ Отмена", "a:main")]),
    )


@router.callback_query(Panel.broadcast, F.data.startswith("a:bc:go:"))
async def bc_go(
    call: CallbackQuery, bot: Bot, db: Database, settings: Settings,
    state: FSMContext, broadcaster: Broadcaster,
) -> None:
    data = await state.get_data()
    await state.clear()
    message = data.get("bc")
    if not message:
        await call.answer("Сообщение потерялось, начните заново", show_alert=True)
        return
    if broadcaster.running:
        await call.answer("Рассылка уже идёт", show_alert=True)
        return
    ids = await db.audience(AUDIENCES[call.data.rsplit(":", 1)[1]][1])
    await settings.set("last_broadcast", int(time.time()))
    await call.message.edit_text(f"📨 Рассылка начата: {len(ids)} получателей…", reply_markup=STOP_KB)
    await call.answer()
    broadcaster.start(bot, db, message, ids, call.message.chat.id, call.message.message_id)


@router.callback_query(F.data == "a:bc:stop")
async def bc_stop(call: CallbackQuery, broadcaster: Broadcaster) -> None:
    broadcaster.stop()
    await call.answer("Останавливаю…")
