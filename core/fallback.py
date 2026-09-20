"""Страховка от «мёртвых» кнопок.

Если ни один модуль не взялся за нажатие, Telegram продолжает крутить
часики на кнопке, а в логах не остаётся ничего: снаружи это выглядит как
зависший бот. Роутер подключается последним, отвечает человеку понятной
фразой и пишет в лог, какой именно callback остался без обработчика.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from core.logging import get_logger
from texts.service import TextService

log = get_logger(__name__)

router = Router(name="fallback")


@router.callback_query()
async def on_unhandled_callback(callback: CallbackQuery, texts: TextService) -> None:
    """Нажатие, до которого не добрался ни один модуль."""
    message = callback.message
    chat = message.chat if message is not None else None
    chat_id = chat.id if chat is not None and chat.type != "private" else None

    log.warning(
        "нажатие без обработчика",
        extra={
            "callback_data": callback.data,
            "chat_type": chat.type if chat is not None else None,
        },
    )

    content = await texts.render(chat_id, "callback_unknown")
    await callback.answer(content.text, show_alert=True)
