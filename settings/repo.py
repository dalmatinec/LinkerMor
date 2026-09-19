"""Доступ к таблицам настроек."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from settings.models import ChatSetting, SettingAudit, SystemSetting


class SettingsRepository:
    """Чтение и запись переопределений настроек."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_overrides(self, chat_id: int) -> dict[str, Any]:
        """Все переопределения чата одним запросом.

        Настройки читаются целиком, а не по одной: запросов столько же, а
        последующие обращения обслуживаются кешем без похода в базу.
        """
        stmt = select(ChatSetting.key, ChatSetting.value).where(ChatSetting.chat_id == chat_id)
        return {key: value for key, value in (await self._session.execute(stmt)).all()}

    async def get_override(self, chat_id: int, key: str) -> Any | None:
        stmt = select(ChatSetting.value).where(
            ChatSetting.chat_id == chat_id, ChatSetting.key == key
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert(self, chat_id: int, key: str, value: Any, actor_id: int | None) -> None:
        stmt = (
            insert(ChatSetting)
            .values(chat_id=chat_id, key=key, value=value, updated_by=actor_id)
            .on_conflict_do_update(
                index_elements=[ChatSetting.chat_id, ChatSetting.key],
                set_={"value": value, "updated_by": actor_id, "updated_at": func.now()},
            )
        )
        await self._session.execute(stmt)

    async def delete(self, chat_id: int, key: str) -> None:
        """Убрать переопределение: настройка вернётся к значению по умолчанию."""
        await self._session.execute(
            delete(ChatSetting).where(ChatSetting.chat_id == chat_id, ChatSetting.key == key)
        )

    async def record_change(
        self, chat_id: int, key: str, old: Any, new: Any, actor_id: int | None
    ) -> None:
        self._session.add(
            SettingAudit(chat_id=chat_id, key=key, old_value=old, new_value=new, actor_id=actor_id)
        )

    async def history(self, chat_id: int, limit: int = 20) -> list[SettingAudit]:
        stmt = (
            select(SettingAudit)
            .where(SettingAudit.chat_id == chat_id)
            .order_by(SettingAudit.created_at.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())


class SystemSettingsRepository:
    """Общесистемные настройки владельца бота."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_all(self) -> dict[str, Any]:
        stmt = select(SystemSetting.key, SystemSetting.value)
        return {key: value for key, value in (await self._session.execute(stmt)).all()}

    async def upsert(self, key: str, value: Any, actor_id: int | None) -> None:
        stmt = (
            insert(SystemSetting)
            .values(key=key, value=value, updated_by=actor_id)
            .on_conflict_do_update(
                index_elements=[SystemSetting.key],
                set_={"value": value, "updated_by": actor_id, "updated_at": func.now()},
            )
        )
        await self._session.execute(stmt)
