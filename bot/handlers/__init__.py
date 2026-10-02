from aiogram import Router

from bot.handlers import admin, group, moderation, user


def build_router() -> Router:
    """Порядок важен: админка (её состояния) → бан/ID → группа → пользователи."""
    root = Router(name="root")
    root.include_routers(admin.router, moderation.router, group.router, user.router)
    return root
