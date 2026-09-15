"""Админ-команды: пул мемов, тексты, триггеры, тумблер и статистика."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Database
from bot.filters import IsAdmin
from bot.handlers.greeting import render_greeting
from bot.media import HUMAN_KIND, extract_media, send_media

logger = logging.getLogger(__name__)
router = Router(name="admin")

PUBLIC_HELP = (
    "Привет! Напиши мне <b>/start</b> — и я кину мемчик. 🙂"
)

ADMIN_HELP = """<b>Команды админа</b>

<b>Мемы</b>
/addmeme — ответь этой командой на медиа или пришли медиа с такой подписью
/memes — листалка по пулу с кнопкой удаления
/delmeme &lt;id&gt; — удалить по номеру

<b>Тексты и триггеры</b>
/settext &lt;текст&gt; — приветствие. Подстановки: {name}, {mention}. Можно HTML
/triggers — список слов-триггеров
/addtrigger &lt;фраза&gt; — добавить
/deltrigger &lt;фраза&gt; — убрать

<b>Поведение</b>
/cooldown &lt;минут&gt; — пауза между ответами одному человеку (0 — без паузы)
/on, /off — включить или выключить автоответы
/stats — статистика

Триггеры в группах работают, только если в @BotFather выключен Group Privacy."""


class MemeNav(CallbackData, prefix="mnav"):
    action: str  # go | del | noop
    offset: int


def _nav_keyboard(meme_id: int, offset: int, total: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️", callback_data=MemeNav(action="go", offset=offset - 1))
    builder.button(
        text=f"#{meme_id} · {offset + 1}/{total}",
        callback_data=MemeNav(action="noop", offset=offset),
    )
    builder.button(text="▶️", callback_data=MemeNav(action="go", offset=offset + 1))
    builder.button(
        text="🗑 Удалить", callback_data=MemeNav(action="del", offset=offset)
    )
    builder.adjust(3, 1)
    return builder.as_markup()


async def _show_meme(message: Message, db: Database, offset: int) -> None:
    """Показывает один мем из пула с кнопками навигации.

    Номер и позиция живут в подписи к средней кнопке, а не в caption:
    у стикеров и кружков подписи нет, а клавиатура есть у всех типов.
    """
    total = await db.count_memes()
    if total == 0:
        await message.answer("Пул пуст. Кинь мне картинку с подписью /addmeme.")
        return

    offset %= total
    meme = await db.meme_at(offset)
    if meme is None:
        await message.answer("Не нашёл мем на этой позиции, попробуй /memes заново.")
        return

    try:
        await send_media(
            message,
            meme["file_id"],
            meme["kind"],
            meme["caption"],
            reply_markup=_nav_keyboard(meme["id"], offset, total),
        )
    except TelegramBadRequest as exc:
        logger.warning("Мем #%s не показался (%s)", meme["id"], exc)
        await db.mark_broken(meme["id"])
        await message.answer(
            f"Мем #{meme['id']} не открывается, пометил битым. Полистай дальше: /memes"
        )


@router.message(Command("help"))
async def cmd_help(
    message: Message, db: Database, admin_ids: frozenset[int]
) -> None:
    user = message.from_user
    if user is not None and user.id in admin_ids:
        await message.answer(ADMIN_HELP)
    else:
        await message.answer(PUBLIC_HELP)


@router.message(Command("addmeme"), IsAdmin())
async def cmd_addmeme(
    message: Message, command: CommandObject, db: Database
) -> None:
    if message.reply_to_message is not None:
        source = message.reply_to_message
        caption = command.args or source.caption
    else:
        # Медиа прислали с подписью «/addmeme ...» — сама команда в подписи не нужна.
        source = message
        caption = command.args

    media = extract_media(source)
    if media is None:
        await message.answer(
            "Не вижу медиа. Ответь командой на картинку, гифку, видео или стикер — "
            "либо пришли медиа, подписав его <code>/addmeme</code>."
        )
        return

    user = message.from_user
    meme_id = await db.add_meme(
        media.file_id,
        media.file_unique_id,
        media.kind,
        caption,
        user.id if user else None,
    )
    if meme_id is None:
        await message.answer("Этот мем уже есть в пуле. 🤷")
        return

    kind = HUMAN_KIND.get(media.kind, media.kind)
    total = await db.count_memes()
    await message.answer(f"✅ Добавил {kind} как мем #{meme_id}. Всего в пуле: {total}.")


@router.message(Command("memes"), IsAdmin())
async def cmd_memes(message: Message, db: Database) -> None:
    await _show_meme(message, db, 0)


@router.callback_query(MemeNav.filter(), IsAdmin())
async def on_meme_nav(
    callback: CallbackQuery, callback_data: MemeNav, db: Database
) -> None:
    if callback_data.action == "noop":
        await callback.answer()
        return

    message = callback.message
    if message is None:
        await callback.answer("Сообщение слишком старое", show_alert=True)
        return

    offset = callback_data.offset
    if callback_data.action == "del":
        meme = await db.meme_at(offset)
        if meme is not None and await db.delete_meme(meme["id"]):
            await callback.answer(f"Мем #{meme['id']} удалён")
        else:
            await callback.answer("Уже удалён")

    # Медиа разных типов друг в друга не редактируются — проще удалить и прислать заново.
    try:
        await message.delete()
    except TelegramBadRequest:
        logger.debug("Не смог удалить сообщение листалки, шлю новое")

    await _show_meme(message, db, offset)
    await callback.answer()


@router.message(Command("delmeme"), IsAdmin())
async def cmd_delmeme(
    message: Message, command: CommandObject, db: Database
) -> None:
    raw = (command.args or "").strip().lstrip("#")
    if not raw.isdigit():
        await message.answer("Формат: <code>/delmeme 12</code>. Номера видно в /memes.")
        return
    if await db.delete_meme(int(raw)):
        await message.answer(f"🗑 Мем #{raw} удалён. В пуле: {await db.count_memes()}.")
    else:
        await message.answer(f"Мема #{raw} нет в пуле.")


@router.message(Command("settext"), IsAdmin())
async def cmd_settext(
    message: Message, command: CommandObject, db: Database
) -> None:
    text = (command.args or "").strip()
    if not text:
        current = await db.greeting_text()
        await message.answer(
            "Сейчас приветствие такое:\n\n"
            f"<code>{current}</code>\n\n"
            "Поменять: <code>/settext Дарова, {name}!</code>"
        )
        return

    user = message.from_user
    if user is None:
        return

    # Проверяем разметку до сохранения: если HTML кривой, Telegram не примет
    # сообщение — и лучше об этом узнать сейчас, а не на первом же госте.
    try:
        await message.answer("Так это будет выглядеть:")
        await message.answer(render_greeting(text, user))
    except TelegramBadRequest as exc:
        await message.answer(
            f"Не сохранил — Telegram не принял разметку: {exc}\n"
            "Старое приветствие осталось на месте.",
            parse_mode=None,
        )
        return

    await db.set_setting("greeting_text", text)
    await message.answer("✅ Сохранил.")


@router.message(Command("triggers"), IsAdmin())
async def cmd_triggers(message: Message, db: Database) -> None:
    phrases = await db.list_triggers()
    if not phrases:
        await message.answer(
            "Триггеров нет — бот отвечает только на /start.\n"
            "Добавить: <code>/addtrigger старт</code>"
        )
        return
    listing = "\n".join(f"• {p}" for p in phrases)
    await message.answer(
        f"<b>Слова-триггеры</b>\n{listing}\n\n"
        "В группах они работают только при выключенном Group Privacy."
    )


@router.message(Command("addtrigger"), IsAdmin())
async def cmd_addtrigger(
    message: Message, command: CommandObject, db: Database
) -> None:
    phrase = (command.args or "").strip().lower()
    if not phrase:
        await message.answer("Формат: <code>/addtrigger старт</code>")
        return
    if await db.add_trigger(phrase):
        await message.answer(f"✅ Теперь реагирую на «{phrase}».")
    else:
        await message.answer(f"«{phrase}» уже в списке.")


@router.message(Command("deltrigger"), IsAdmin())
async def cmd_deltrigger(
    message: Message, command: CommandObject, db: Database
) -> None:
    phrase = (command.args or "").strip().lower()
    if not phrase:
        await message.answer("Формат: <code>/deltrigger старт</code>")
        return
    if await db.delete_trigger(phrase):
        await message.answer(f"🗑 Убрал «{phrase}».")
    else:
        await message.answer(f"«{phrase}» и так не было.")


@router.message(Command("cooldown"), IsAdmin())
async def cmd_cooldown(
    message: Message, command: CommandObject, db: Database
) -> None:
    raw = (command.args or "").strip()
    if not raw:
        current = await db.cooldown_minutes()
        await message.answer(
            f"Сейчас пауза: <b>{current}</b> мин.\n"
            "Поменять: <code>/cooldown 60</code>. Ноль — отвечать всегда."
        )
        return
    if not raw.isdigit():
        await message.answer("Нужно целое число минут, например: <code>/cooldown 60</code>")
        return

    minutes = int(raw)
    await db.set_setting("cooldown_minutes", str(minutes))
    if minutes == 0:
        await message.answer("✅ Пауза убрана — отвечаю на каждый /start.")
    else:
        await message.answer(
            f"✅ Одному человеку в одном чате отвечаю не чаще раза в {minutes} мин."
        )


@router.message(Command("on"), IsAdmin())
async def cmd_on(message: Message, db: Database) -> None:
    await db.set_enabled(True)
    await message.answer("🟢 Автоответы включены.")


@router.message(Command("off"), IsAdmin())
async def cmd_off(message: Message, db: Database) -> None:
    await db.set_enabled(False)
    await message.answer("🔴 Автоответы выключены. Вернуть: /on")


@router.message(Command("stats"), IsAdmin())
async def cmd_stats(message: Message, db: Database) -> None:
    s = await db.stats()
    enabled = "🟢 включены" if await db.is_enabled() else "🔴 выключены"
    broken = f"\nБитых мемов: {s['broken']}" if s["broken"] else ""
    await message.answer(
        f"<b>Статистика</b>\n"
        f"Автоответы: {enabled}\n"
        f"Мемов в пуле: {s['memes']}{broken}\n"
        f"Триггеров: {s['triggers']}\n"
        f"Пауза: {await db.cooldown_minutes()} мин\n\n"
        f"Ответов за сутки: {s['greets_day']}\n"
        f"Ответов всего: {s['greets_total']}\n"
        f"Чатов: {s['chats']} · людей: {s['users']}"
    )
