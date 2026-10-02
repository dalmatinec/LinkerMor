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


BACK_BTN = btn("⬅️ Назад", "a:main")
BACK = [BACK_BTN]
CANCEL_KB = kb([btn("✖️ Отмена", "a:main")])
ON = {True: "вкл", False: "выкл"}
DOT = {True: "🟢", False: "🔴"}
FLOOD_STEPS = {"flood_limit": 1, "flood_window": 5, "flood_mute": 10}
SEND_ANY = (
    "Текст, фото, видео, GIF, файл, голосовое или стикер. "
    "Форматирование и премиум-эмодзи сохранятся.\n\n"
    "<i>/cancel для отмены</i>"
)


def pairs(buttons: list[InlineKeyboardButton]) -> list[list[InlineKeyboardButton]]:
    """Разложить кнопки по две в ряд."""
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


async def show(target: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Обновить панель на месте, а если нельзя, прислать заново."""
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
    return f"<b>{escape(settings['group_title'] or str(settings.group_id))}</b>"


# ---- главное меню -----------------------------------------------------------

def main_view(settings: Settings, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "⚙️ <b>Админка</b>\n\n"
        f"👥 Группа: {group_name(settings)}\n"
        f"{DOT[settings['captcha']]} Капча\n"
        f"{DOT[settings['start_ad_on']]} Реклама при старте\n"
        f"🛡 Флуд: {settings['flood_limit']} за {settings['flood_window']}с, "
        f"пауза {settings['flood_mute']}с"
    )
    buttons = [
        btn("👋 Приветствие", "a:wel"), btn("📢 Реклама", "a:ad"),
        btn("📨 Рассылка", "a:bc"), btn("👥 Группа", "a:grp"),
        btn(f"{DOT[settings['captcha']]} Капча", "a:cap"), btn("🛡 Антифлуд", "a:fl"),
        btn("🚫 Баны", "a:ban"), btn("📊 Статистика", "a:st"),
    ]
    if settings.is_owner(user_id):
        buttons.append(btn("👮 Админы", "a:adm"))
    buttons.append(btn("✖️ Закрыть", "a:close"))
    return text, kb(*pairs(buttons))


@router.message(Command("admin", "panel"), F.chat.type == "private")
async def open_panel(message: Message, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await show(message, *main_view(settings, message.from_user.id))


@router.message(Command("cancel"), F.chat.type == "private")
async def cancel(message: Message, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено", reply_markup=ReplyKeyboardRemove())
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
            f"Сейчас: {escape(stored.describe(value)) if value else 'стандартное'}\n\n"
            "<i>Приходит после /start и капчи.</i>"
        )
        rows = [
            [btn("✏️ Изменить", "a:wel:set"), btn("👁 Показать", "a:wel:show")],
            [btn("♻️ Сбросить", "a:wel:del"), BACK_BTN],
        ]
    else:
        value = settings["start_ad"]
        on = settings["start_ad_on"]
        text = (
            f"📢 <b>Реклама при старте</b> {DOT[on]}\n\n"
            f"Сейчас: {escape(stored.describe(value))}\n\n"
            "<i>Приходит сразу после приветствия.</i>"
        )
        rows = [
            [btn("✏️ Изменить", "a:ad:set"), btn("👁 Показать", "a:ad:show")],
            [btn("🔴 Выключить" if on else "🟢 Включить", "a:ad:toggle"),
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
    title = "приветствие" if kind == "wel" else "рекламу"
    await show(call, f"✏️ <b>Пришлите {title}</b>\n\n{SEND_ANY}", CANCEL_KB)


@router.message(StateFilter(Panel.welcome, Panel.ad), F.chat.type == "private")
async def stored_save(message: Message, settings: Settings, state: FSMContext) -> None:
    kind = "wel" if await state.get_state() == Panel.welcome.state else "ad"
    try:
        value = stored.from_message(message)
    except stored.UnsupportedMessage:
        await message.answer("Такой тип не подходит, пришлите другое или /cancel")
        return
    await settings.set(KEYS[kind], value)
    if kind == "ad":
        await settings.set("start_ad_on", True)
    await state.clear()
    await message.answer("✅ Сохранено")
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
        "<i>Отвечайте реплаем на сообщение пользователя. Чтобы сменить группу, "
        "добавьте в неё бота админом и нажмите Выбрать, или напишите "
        "/setgroup в самой группе.</i>"
    )
    buttons = [btn("📌 Выбрать", "a:grp:pick")]
    if settings.group_id is not None:
        buttons.append(btn("🧪 Проверить", "a:grp:test"))
    return text, kb(*pairs(buttons), BACK)


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
        "👇 Нажмите кнопку внизу и выберите группу, где уже есть бот",
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
    await message.answer("Отменено", reply_markup=ReplyKeyboardRemove())
    await show(message, *group_view(settings))


async def _bind_group(
    reply_to: Message, bot: Bot, settings: Settings, chat_id: int, title: str | None
) -> None:
    try:
        await bot.send_message(chat_id, "✅ Теперь это рабочая группа")
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await reply_to.answer(
            f"❌ Бот не может писать в эту группу: {escape(exc.message)}",
            parse_mode="HTML", reply_markup=ReplyKeyboardRemove(),
        )
        return
    await settings.set("group_id", chat_id)
    await settings.set("group_title", title)
    await reply_to.answer("✅ Группа выбрана", reply_markup=ReplyKeyboardRemove())
    if reply_to.chat.type == "private":
        await show(reply_to, *group_view(settings))


@router.message(Command("setgroup"), F.chat.type.in_({"group", "supergroup"}))
async def set_group_here(message: Message, bot: Bot, settings: Settings) -> None:
    await _bind_group(message, bot, settings, message.chat.id, message.chat.title)


@router.callback_query(F.data == "a:grp:test")
async def group_test(call: CallbackQuery, bot: Bot, settings: Settings) -> None:
    try:
        await bot.send_message(settings.group_id, "🧪 Проверка связи, бот на месте")
        await call.answer("✅ Связь есть, сообщение в группе", show_alert=True)
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
        f"Больше <b>{settings['flood_limit']}</b> сообщений за "
        f"<b>{settings['flood_window']}с</b>: пауза <b>{settings['flood_mute']}с</b>\n\n"
        "<i>Альбом считается одним сообщением. Лимиты Telegram на отправку "
        "бот соблюдает сам.</i>"
    )
    rows = []
    for key, label, unit in (
        ("flood_limit", "Сообщений", ""),
        ("flood_window", "Окно", "с"),
        ("flood_mute", "Пауза", "с"),
    ):
        step = FLOOD_STEPS[key]
        rows.append([
            btn("➖", f"a:fl:{key}:-{step}"),
            btn(f"{label}: {settings[key]}{unit}", "a:fl"),
            btn("➕", f"a:fl:{key}:{step}"),
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
    lines = [f"🚫 <b>Баны</b> · {len(banned)}", ""]
    if not banned:
        lines.append("Пусто")
    for u in banned:
        reason = f": {escape(u.ban_reason)}" if u.ban_reason else ""
        lines.append(f"• {escape(u.full_name)} <code>{u.id}</code>{reason}")
    lines += [
        "",
        "<i>ID видно на кнопке 👤 под сообщением в группе или по /id реплаем. "
        "Команды /ban ID и /unban ID работают везде.</i>",
    ]
    unban = [btn(f"✅ {u.id}", f"a:unb:{u.id}") for u in banned]
    return "\n".join(lines), kb(*pairs(unban), [btn("➕ Забанить", "a:ban:add"), BACK_BTN])


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
    await show(call, "🚫 Пришлите ID и причину, если нужна:\n<code>123456789 спам</code>", CANCEL_KB)


@router.message(Panel.ban_id, F.text)
async def bans_add(message: Message, db: Database, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if not parts or not parts[0].lstrip("-").isdigit():
        await message.answer("Нужен числовой ID, попробуйте ещё раз или /cancel")
        return
    await db.set_banned(int(parts[0]), True, parts[1] if len(parts) > 1 else None)
    await state.clear()
    await show(message, *await bans_view(db))


@router.message(Panel.ban_id)
async def bans_add_not_text(message: Message) -> None:
    await message.answer("Нужен числовой ID текстом, попробуйте ещё раз или /cancel")


# ---- статистика --------------------------------------------------------------

@router.callback_query(F.data == "a:st")
async def stats(call: CallbackQuery, db: Database) -> None:
    s = await db.stats()
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👤 Всего: <b>{s['total']}</b>\n"
        f"✅ Прошли капчу: <b>{s['passed']}</b>\n"
        f"🔥 За сутки: <b>{s['day']}</b>\n"
        f"📅 За неделю: <b>{s['week']}</b>\n"
        f"💬 Сообщений: <b>{s['messages']}</b>\n"
        f"💤 Остановили бота: <b>{s['blocked']}</b>\n"
        f"🚫 В бане: <b>{s['banned']}</b>"
    )
    await show(call, text, kb([btn("🔄 Обновить", "a:st"), BACK_BTN]))


# ---- админы (только владелец) ------------------------------------------------

def admins_view(settings: Settings) -> tuple[str, InlineKeyboardMarkup]:
    owners = ", ".join(f"<code>{i}</code>" for i in sorted(settings.owner_ids))
    admins = sorted(settings.admins - set(settings.owner_ids))
    lines = ["👮 <b>Админы</b>", "", f"👑 {owners}"]
    lines += [f"• <code>{a}</code>" for a in admins]
    lines.append("\n<i>Админы могут всё, кроме управления админами.</i>")
    remove = [btn(f"🗑 {a}", f"a:adm:del:{a}") for a in admins]
    return "\n".join(lines), kb(*pairs(remove), [btn("➕ Добавить", "a:adm:add"), BACK_BTN])


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
    await show(call, "👮 Пришлите ID нового админа или перешлите его сообщение", CANCEL_KB)


@router.message(Panel.admin_id, is_owner)
async def admins_add(message: Message, settings: Settings, state: FSMContext) -> None:
    new_id = None
    if isinstance(message.forward_origin, MessageOriginUser):
        new_id = message.forward_origin.sender_user.id
    elif message.text and message.text.strip().isdigit():
        new_id = int(message.text.strip())
    if new_id is None:
        await message.answer(
            "Не вижу ID. Если пересылка скрыта, пришлите ID числом "
            "или /cancel"
        )
        return
    await settings.add_admin(new_id, message.from_user.id)
    await state.clear()
    await show(message, *admins_view(settings))


@router.callback_query(F.data.startswith("a:adm"))
async def admins_denied(call: CallbackQuery) -> None:
    await call.answer("Только для владельца", show_alert=True)


# ---- рассылка ----------------------------------------------------------------

AUDIENCES = {
    "0": ("👥 Всем", None),
    "30": ("📅 Активным за 30 дней", 30),
    "7": ("🔥 Активным за 7 дней", 7),
}


def _ago(ts: int) -> str:
    if not ts:
        return "не было"
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
        f"Последняя: {_ago(settings['last_broadcast'])}\n\n"
        f"Пришлите сообщение. {SEND_ANY}",
        CANCEL_KB,
    )


@router.message(Panel.broadcast, F.chat.type == "private")
async def bc_preview(message: Message, bot: Bot, db: Database, state: FSMContext) -> None:
    try:
        value = stored.from_message(message)
    except stored.UnsupportedMessage:
        await message.answer("Такой тип не подходит, пришлите другое или /cancel")
        return
    await state.update_data(bc=value)
    await message.answer("👁 Так увидят пользователи:")
    await stored.send(bot, message.chat.id, value)
    rows = []
    for key, (label, days) in AUDIENCES.items():
        count = len(await db.audience(days))
        rows.append([btn(f"{label} · {count}", f"a:bc:aud:{key}")])
    rows.append([btn("✖️ Отмена", "a:main")])
    await message.answer("📨 <b>Кому отправить?</b>", parse_mode="HTML", reply_markup=kb(*rows))


@router.callback_query(Panel.broadcast, F.data.startswith("a:bc:aud:"))
async def bc_confirm(call: CallbackQuery, db: Database, settings: Settings, state: FSMContext) -> None:
    key = call.data.rsplit(":", 1)[1]
    label, days = AUDIENCES[key]
    count = len(await db.audience(days))
    warn = ""
    if settings["last_broadcast"] and time.time() - settings["last_broadcast"] < 86400:
        warn = (
            f"\n\n⚠️ Прошлая рассылка была {_ago(settings['last_broadcast'])}. "
            "Из-за частых рассылок люди останавливают бота."
        )
    await show(
        call,
        f"📨 {label}: <b>{count}</b> чел.\nОтправляем?{warn}",
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
    await call.message.edit_text(f"📨 Рассылка запущена, получателей: {len(ids)}", reply_markup=STOP_KB)
    await call.answer()
    broadcaster.start(bot, db, message, ids, call.message.chat.id, call.message.message_id)


@router.callback_query(F.data == "a:bc:stop")
async def bc_stop(call: CallbackQuery, broadcaster: Broadcaster) -> None:
    broadcaster.stop()
    await call.answer("Останавливаю")
