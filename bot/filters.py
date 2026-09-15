"""Фильтры: проверка админа и матчинг слов-триггеров."""
from __future__ import annotations

import re
from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.db import Database


def matches_trigger(text: str, phrases: list[str]) -> bool:
    """Ищет фразу в тексте по границам слова.

    «старт» ловится в «старт» и «Старт!», но не в «стартап» и не в «рестарт» —
    иначе в группе бот здоровался бы на каждое второе сообщение.
    """
    if not text or not phrases:
        return False
    haystack = text.lower()
    for phrase in phrases:
        phrase = phrase.strip().lower()
        if not phrase:
            continue
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
        if re.search(pattern, haystack):
            return True
    return False


class IsAdmin(BaseFilter):
    """Годится и для сообщений, и для нажатий на инлайн-кнопки."""

    async def __call__(self, event: Message | CallbackQuery, **data: Any) -> bool:
        admin_ids: frozenset[int] = data.get("admin_ids", frozenset())
        user = event.from_user
        return user is not None and user.id in admin_ids


class HasTrigger(BaseFilter):
    async def __call__(self, message: Message, **data: Any) -> bool:
        text = message.text or message.caption or ""
        if not text or text.startswith("/"):
            return False
        db: Database = data["db"]
        return matches_trigger(text, await db.list_triggers())
