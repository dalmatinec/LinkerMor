from aiogram import Router

from bot.handlers import admin, group, hidden, moderation, user


def build_router() -> Router:
    """Порядок важен: админка, бан и ID, скрытые команды, группа, пользователи."""
    root = Router(name="root")
    root.include_routers(
        admin.router, moderation.router, hidden.router, group.router, user.router
    )
    return root
