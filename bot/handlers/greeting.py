"""Основная логика: на /start и на слова-триггеры — случайный мем плюс привет."""
from __future__ import annotations

import html
import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import Message, User

from bot.db import Database
from bot.filters import HasTrigger
from bot.media import send_media

logger = logging.getLogger(__name__)
router = Router(name="greeting")

# Сколько битых file_id подряд готовы пережить, прежде чем ответить без мема.
MAX_MEME_ATTEMPTS = 5


def render_greeting(template: str, user: User) -> str:
    """Подставляет {name} и {mention}.

    Через replace, а не format: в шаблоне админа могут быть свои фигурные
    скобки, и format на них упал бы.
    """
    name = user.first_name or "друг"
    return template.replace("{name}", html.escape(name)).replace(
        "{mention}", user.mention_html(name)
    )


async def _send_random_meme(message: Message, db: Database) -> int | None:
    """Шлёт случайный мем. Битые file_id помечает и пробует следующий."""
    for _ in range(MAX_MEME_ATTEMPTS):
        meme = await db.pick_meme(message.chat.id)
        if meme is None:
            return None
        try:
            await send_media(message, meme["file_id"], meme["kind"], meme["caption"])
        except TelegramBadRequest as exc:
            logger.warning("Мем #%s не отправился (%s), помечаю битым", meme["id"], exc)
            await db.mark_broken(meme["id"])
            continue
        await db.set_last_meme(message.chat.id, meme["id"])
        return meme["id"]
    return None


async def greet(message: Message, db: Database, admin_ids: frozenset[int]) -> None:
    user = message.from_user
    if user is None or user.is_bot:
        return

    if not await db.is_enabled():
        logger.debug("Бот выключен, молчу")
        return

    cooldown = await db.cooldown_minutes()
    if not await db.can_greet(message.chat.id, user.id, cooldown):
        logger.debug("Кулдаун для %s в чате %s", user.id, message.chat.id)
        return

    meme_id = await _send_random_meme(message, db)

    text = render_greeting(await db.greeting_text(), user)
    try:
        await message.answer(text)
    except TelegramBadRequest:
        # Кривая разметка в шаблоне — отправляем как есть, без HTML.
        logger.warning("Приветствие не разобралось как HTML, шлю текстом")
        await message.answer(text, parse_mode=None)

    await db.log_greet(message.chat.id, user.id, meme_id)

    if meme_id is None and user.id in admin_ids and await db.count_memes() == 0:
        await message.answer(
            "☝️ Пул мемов пуст. Кинь мне картинку с подписью <code>/addmeme</code> "
            "или ответь на неё этой командой."
        )


@router.message(CommandStart())
async def on_start(message: Message, db: Database, admin_ids: frozenset[int]) -> None:
    await greet(message, db, admin_ids)


@router.message(HasTrigger())
async def on_trigger(message: Message, db: Database, admin_ids: frozenset[int]) -> None:
    await greet(message, db, admin_ids)
