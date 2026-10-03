"""Сквозные сценарии: апдейт → диспетчер → вызовы Bot API."""

from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    SendMessage,
    SendPhoto,
    SetMessageReaction,
)
from aiogram.types import PhotoSize

from tests.conftest import GROUP, OWNER, STAFF

USER = 555


async def test_start_requires_captcha_before_welcome_and_group(h):
    await h.feed(h.message(USER, "/start"))

    sent = h.session.of(SendMessage)
    assert len(sent) == 1 and "Проверка" in sent[0].text
    assert not h.session.of(SendMessage, GROUP), "до капчи в группу ничего не уходит"

    ch = h.dp["captchas"].get(USER)
    await h.feed(h.callback(USER, f"cap:{ch.answer}"))

    to_user = [m.text for m in h.session.of(SendMessage, USER)]
    assert any("Здравствуйте" in t for t in to_user), "приветствие после капчи"
    card = h.session.of(SendMessage, GROUP)
    assert len(card) == 1 and "Новый пользователь" in card[0].text and str(USER) in card[0].text
    assert (await h.db.get_user(USER)).captcha_passed


async def test_wrong_captcha_three_times_locks(h):
    await h.feed(h.message(USER, "/start"))
    for _ in range(3):
        ch = h.dp["captchas"].get(USER)
        await h.feed(h.callback(USER, f"cap:{ch.answer + 100}"))
    assert h.dp["captchas"].locked_for(USER) > 0
    assert not h.session.of(SendMessage, GROUP)


async def test_messages_before_captcha_are_not_forwarded(h):
    await h.feed(h.message(USER, "/start"))
    await h.feed(h.message(USER, "вопрос"))
    assert not h.session.of(CopyMessage, GROUP)


async def test_repeat_start_is_marked_repeat(h):
    await h.start_and_pass(USER)
    await h.feed(h.message(USER, "/start"))
    cards = h.session.of(SendMessage, GROUP)
    assert "Снова" in cards[-1].text


async def test_captcha_off_goes_straight_to_welcome(h):
    await h.settings.set("captcha", False)
    await h.feed(h.message(USER, "/start"))
    assert any("Здравствуйте" in m.text for m in h.session.of(SendMessage, USER))
    assert "Новый" in h.session.of(SendMessage, GROUP)[0].text


async def test_user_message_copied_and_staff_reply_delivered(h):
    await h.start_and_pass(USER)
    msg = h.message(USER, "<b>жирный</b>")
    await h.feed(msg)

    copy = h.session.of(CopyMessage, GROUP)[-1]
    assert copy.from_chat_id == USER and copy.message_id == msg.message_id
    assert copy.reply_markup.inline_keyboard[0][0].callback_data == f"who:{USER}"

    link = await h.db.by_group_message(GROUP, max(
        gm for gm in [r for r in await _group_ids(h)]
    ))
    assert link == (USER, msg.message_id)

    group_msg_id = (await _group_ids(h))[-1]
    reply = h.message(STAFF, "ответ", chat_id=GROUP, reply_to=group_msg_id)
    await h.feed(reply)

    to_user = h.session.of(CopyMessage, USER)[-1]
    assert to_user.from_chat_id == GROUP and to_user.message_id == reply.message_id
    assert to_user.reply_parameters.message_id == msg.message_id
    assert h.session.of(SetMessageReaction, GROUP), "в группе отмечено, что ответ ушёл"


async def test_any_number_of_staff_can_reply_many_times(h):
    await h.start_and_pass(USER)
    await h.feed(h.message(USER, "вопрос"))
    group_msg_id = (await _group_ids(h))[-1]
    for staff in range(3000, 3010):
        await h.feed(h.message(staff, "ответ", chat_id=GROUP, reply_to=group_msg_id))
    assert len(h.session.of(CopyMessage, USER)) == 10


async def test_user_reply_to_answer_continues_thread(h):
    await h.start_and_pass(USER)
    await h.feed(h.message(USER, "вопрос"))
    group_msg_id = (await _group_ids(h))[-1]
    staff_msg = h.message(STAFF, "ответ", chat_id=GROUP, reply_to=group_msg_id)
    await h.feed(staff_msg)

    # ID копии у пользователя записан в user_map
    cur = await h.db.conn.execute("SELECT user_msg_id FROM user_map")
    user_side = (await cur.fetchone())[0]
    await h.feed(h.message(USER, "уточнение", reply_to=user_side))
    last = h.session.of(CopyMessage, GROUP)[-1]
    assert last.reply_parameters.message_id == staff_msg.message_id


async def test_reply_to_unrelated_group_message_ignored(h):
    await h.feed(h.message(STAFF, "болтовня", chat_id=GROUP, reply_to=99999))
    assert not h.session.of(CopyMessage)


async def test_reply_to_blocked_user_reports_in_group(h):
    await h.start_and_pass(USER)
    await h.feed(h.message(USER, "вопрос"))
    group_msg_id = (await _group_ids(h))[-1]
    h.session.blocked.add(USER)
    await h.feed(h.message(STAFF, "ответ", chat_id=GROUP, reply_to=group_msg_id))
    assert "остановил бота" in h.session.of(SendMessage, GROUP)[-1].text
    assert (await h.db.get_user(USER)).blocked_bot


async def test_flood_stops_forwarding_and_warns(h):
    await h.start_and_pass(USER)
    for i in range(6):
        await h.feed(h.message(USER, f"сообщение {i}"))
    assert len(h.session.of(CopyMessage, GROUP)) == 3, "лимит по умолчанию 3"
    warns = [m for m in h.session.of(SendMessage, USER) if "Слишком часто" in m.text]
    assert len(warns) == 1, "предупреждение один раз"
    assert any("флудит" in m.text for m in h.session.of(SendMessage, GROUP))


async def test_album_counts_as_one_message(h):
    await h.start_and_pass(USER)
    photo = [PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)]
    for _ in range(5):
        await h.feed(h.message(USER, None, photo=photo, media_group_id="album1"))
    assert len(h.session.of(CopyMessage, GROUP)) == 5


async def test_banned_user_is_ignored(h):
    await h.start_and_pass(USER)
    await h.feed(h.message(OWNER, f"/ban {USER} спам", chat_id=GROUP))
    assert "забанен" in h.session.of(SendMessage, GROUP)[-1].text
    copies = len(h.session.of(CopyMessage, GROUP))
    await h.feed(h.message(USER, "я снова тут"))
    assert len(h.session.of(CopyMessage, GROUP)) == copies

    await h.feed(h.message(OWNER, f"/unban {USER}", chat_id=GROUP))
    await h.feed(h.message(USER, "спасибо"))
    assert len(h.session.of(CopyMessage, GROUP)) == copies + 1


async def test_ban_by_reply_in_group(h):
    await h.start_and_pass(USER)
    await h.feed(h.message(USER, "вопрос"))
    group_msg_id = (await _group_ids(h))[-1]
    await h.feed(h.message(OWNER, "/ban реклама", chat_id=GROUP, reply_to=group_msg_id))
    user = await h.db.get_user(USER)
    assert user.banned and user.ban_reason == "реклама"


async def test_non_admin_cannot_ban(h):
    await h.feed(h.message(STAFF, f"/ban {USER}", chat_id=GROUP))
    assert not (await h.db.get_user(USER) or type("u", (), {"banned": False})).banned


async def test_id_command_shows_user_id(h):
    await h.start_and_pass(USER)
    await h.feed(h.message(USER, "вопрос"))
    group_msg_id = (await _group_ids(h))[-1]
    await h.feed(h.message(STAFF, "/id", chat_id=GROUP, reply_to=group_msg_id))
    assert str(USER) in h.session.of(SendMessage, GROUP)[-1].text


async def test_ban_button_requires_admin(h):
    await h.feed(h.callback(STAFF, f"ban:{USER}", chat_id=GROUP))
    answer = h.session.of(AnswerCallbackQuery)[-1]
    assert not answer.show_alert and not answer.text, "не админу кнопка молчит"
    assert (await h.db.get_user(USER)) is None

    await h.feed(h.callback(OWNER, f"ban:{USER}", chat_id=GROUP))
    assert (await h.db.get_user(USER)).banned


async def test_admin_sets_welcome_with_media_and_formatting(h):
    from aiogram.types import MessageEntity

    await h.feed(h.callback(OWNER, "a:wel:set"))
    photo = [PhotoSize(file_id="PHOTO", file_unique_id="u", width=1, height=1)]
    entities = [
        MessageEntity(type="bold", offset=0, length=6),
        MessageEntity(type="custom_emoji", offset=7, length=2, custom_emoji_id="5368324170671202286"),
    ]
    await h.feed(h.message(OWNER, None, photo=photo, caption="Привет 😀", caption_entities=entities))
    assert h.settings["welcome"]["type"] == "photo"

    await h.feed(h.message(USER, "/start"))
    ch = h.dp["captchas"].get(USER)
    await h.feed(h.callback(USER, f"cap:{ch.answer}"))
    sent = h.session.of(SendPhoto, USER)[-1]
    assert sent.photo == "PHOTO"
    assert [e.type for e in sent.caption_entities] == ["bold", "custom_emoji"]
    assert sent.caption_entities[1].custom_emoji_id == "5368324170671202286"


async def test_start_ad_sent_after_welcome(h):
    await h.settings.set("captcha", False)
    await h.feed(h.callback(OWNER, "a:ad:set"))
    await h.feed(h.message(OWNER, "🔥 Реклама"))
    assert h.settings["start_ad_on"]
    await h.feed(h.message(USER, "/start"))
    texts = [m.text for m in h.session.of(SendMessage, USER)]
    assert texts[0].startswith("👋") and texts[1] == "🔥 Реклама"


async def test_service_commands_silent_for_non_admin(h):
    await h.start_and_pass(USER)
    h.session.calls.clear()
    for cmd in ("/admin", "/panel", "/cancel", "/ban 1", "/unban 1", "/id", "/setgroup"):
        await h.feed(h.message(USER, cmd))
    assert h.session.calls == [], "ни ответа, ни пересылки в группу"


async def test_non_admin_ban_in_group_is_silent_and_not_forwarded(h):
    await h.start_and_pass(USER)
    await h.feed(h.message(USER, "вопрос"))
    group_msg_id = (await _group_ids(h))[-1]
    h.session.calls.clear()
    await h.feed(h.message(STAFF, "/ban", chat_id=GROUP, reply_to=group_msg_id))
    await h.feed(h.message(STAFF, "/setgroup", chat_id=GROUP))
    assert h.session.calls == []
    assert not (await h.db.get_user(USER)).banned


async def test_admin_still_gets_panel(h):
    await h.feed(h.message(OWNER, "/admin"))
    assert "Админка" in h.session.of(SendMessage, OWNER)[-1].text


async def test_flood_settings_buttons_respect_limits(h):
    for _ in range(10):
        await h.feed(h.callback(OWNER, "a:fl:flood_limit:-1"))
    assert h.settings["flood_limit"] == 1
    await h.feed(h.callback(OWNER, "a:fl:flood_window:5"))
    assert h.settings["flood_window"] == 15


async def test_setgroup_in_group(h):
    await h.feed(h.message(OWNER, "/setgroup", chat_id=-777))
    assert h.settings.group_id == -777


async def test_owner_adds_admin_who_can_ban(h):
    await h.feed(h.callback(OWNER, "a:adm:add"))
    await h.feed(h.message(OWNER, str(STAFF)))
    assert h.settings.is_admin(STAFF)
    await h.feed(h.message(STAFF, f"/ban {USER}", chat_id=GROUP))
    assert (await h.db.get_user(USER)).banned


async def test_admin_cannot_manage_admins(h):
    await h.settings.add_admin(STAFF, OWNER)
    await h.feed(h.callback(STAFF, "a:adm:add"))
    await h.feed(h.message(STAFF, "7777"))
    assert not h.settings.is_admin(7777)


async def test_broadcast_reaches_audience_and_marks_blocked(h):
    for uid in (601, 602, 603):
        await h.start_and_pass(uid)
    await h.db.set_banned(603, True)
    h.session.blocked.add(602)

    await h.feed(h.callback(OWNER, "a:bc"))
    await h.feed(h.message(OWNER, "Новости!"))
    await h.feed(h.callback(OWNER, "a:bc:aud:0"))
    await h.feed(h.callback(OWNER, "a:bc:go:0"))
    await h.dp["broadcaster"]._task

    got = {m.chat_id for m in h.session.of(SendMessage) if m.text == "Новости!"}
    assert got == {OWNER, 601, 602}  # OWNER: предпросмотр
    assert (await h.db.get_user(602)).blocked_bot
    assert h.settings["last_broadcast"] > 0


async def _group_ids(h) -> list[int]:
    cur = await h.db.conn.execute("SELECT group_msg_id FROM group_map ORDER BY rowid")
    return [r[0] for r in await cur.fetchall()]
