"""Личка с пользователем: /start, капча, пересылка сообщений в группу."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import captcha, relay, texts, users
from bot.captcha import CaptchaStore, Challenge
from bot.db import Database, User
from bot.flood import FloodControl, Verdict
from bot.settings import Settings

router = Router(name="user")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


async def _touch(db: Database, message: Message | CallbackQuery) -> tuple[User, bool]:
    u = message.from_user
    return await db.touch_user(u.id, u.first_name, u.last_name, u.username, u.language_code)


def _captcha_markup(ch: Challenge) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=str(v), callback_data=f"cap:{v}") for v in ch.options
    ]])


async def _flood(
    bot: Bot, settings: Settings, flood: FloodControl, message: Message, user: User,
    kind: str = "msg",
) -> bool:
    """True, если сообщение нужно отбросить из-за флуда."""
    verdict, seconds = flood.check(
        user.id,
        settings["flood_limit"],
        settings["flood_window"],
        settings["flood_mute"],
        message.media_group_id,
        kind,
    )
    if verdict is Verdict.OK:
        return False
    if verdict is Verdict.WARN:
        await message.answer(texts.FLOOD_WARN.format(seconds=seconds), parse_mode="HTML")
        if settings.group_id is not None:
            await bot.send_message(
                settings.group_id,
                texts.FLOOD_GROUP.format(name=users.mention(user), id=user.id, seconds=seconds),
                parse_mode="HTML",
            )
    return True


async def _after_captcha(bot: Bot, db: Database, settings: Settings, user: User, new: bool) -> None:
    """Приветствие, реклама и только потом — сообщение в рабочую группу."""
    await relay.send_welcome(bot, settings, user.id)
    await relay.send_start_ad(bot, settings, user.id)
    await relay.send_card(bot, db, settings, user, new)


@router.message(CommandStart())
async def start(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
    flood: FloodControl,
    captchas: CaptchaStore,
) -> None:
    user, _ = await _touch(db, message)
    if user.banned:
        verdict, _ = flood.check(
            user.id, settings["flood_limit"], settings["flood_window"], settings["flood_mute"],
            kind="start",
        )
        if verdict is Verdict.OK:
            await message.answer(texts.BANNED)
        return
    if await _flood(bot, settings, flood, message, user, kind="start"):
        return

    if settings["captcha"] and not user.captcha_passed:
        left = captchas.locked_for(user.id)
        if left:
            await message.answer(texts.CAPTCHA_LOCKED.format(seconds=left))
            return
        ch = captchas.new(user.id)
        await message.answer(
            texts.CAPTCHA.format(question=ch.question),
            parse_mode="HTML",
            reply_markup=_captcha_markup(ch),
        )
        return

    # Первым считается старт, после которого человек впервые прошёл
    # к приветствию; при выключенной капче отметка ставится здесь же.
    new = not user.captcha_passed
    if new:
        await db.set_captcha_passed(user.id)
    await _after_captcha(bot, db, settings, user, new)


@router.callback_query(F.data.startswith("cap:"))
async def captcha_answer(
    call: CallbackQuery, bot: Bot, db: Database, settings: Settings, captchas: CaptchaStore
) -> None:
    user, _ = await _touch(db, call)
    try:
        value = int(call.data.split(":", 1)[1])
    except ValueError:
        await call.answer()
        return

    result = captchas.solve(user.id, value)
    if result is True:
        await call.answer(texts.CAPTCHA_OK)
        await call.message.delete()
        new = not user.captcha_passed
        await db.set_captcha_passed(user.id)
        await _after_captcha(bot, db, settings, user, new)
        return

    if result is False:
        ch = captchas.get(user.id)
        await call.answer(
            texts.CAPTCHA_WRONG.format(attempt=ch.attempts + 1, total=captcha.MAX_ATTEMPTS),
            show_alert=True,
        )
        await call.message.edit_text(
            texts.CAPTCHA.format(question=ch.question),
            parse_mode="HTML",
            reply_markup=_captcha_markup(ch),
        )
        return

    left = captchas.locked_for(user.id)
    text = texts.CAPTCHA_LOCKED.format(seconds=left) if left else texts.CAPTCHA_EXPIRED
    await call.answer(text, show_alert=True)
    await call.message.delete()


@router.message()
async def any_message(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
    flood: FloodControl,
) -> None:
    user, _ = await _touch(db, message)
    if user.banned:
        return  # забаненным не отвечаем, чтобы не тратить лимиты
    if settings["captcha"] and not user.captcha_passed:
        await message.answer(texts.CAPTCHA_REQUIRED)
        return
    if await _flood(bot, settings, flood, message, user):
        return
    if settings.group_id is None:
        await message.answer(texts.NOT_CONFIGURED)
        return
    if not await relay.to_group(bot, db, settings, message, user):
        await message.answer(texts.UNSUPPORTED)
