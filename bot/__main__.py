"""Точка входа: python -m bot"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from bot.config import ConfigError, load_config
from bot.db import Database
from bot.handlers import admin, greeting
from bot.middlewares import AdminMenuMiddleware

logger = logging.getLogger("bot")

PUBLIC_COMMANDS = [
    BotCommand(command="start", description="Мемчик и привет"),
    BotCommand(command="help", description="Что я умею"),
]

ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand(command="addmeme", description="Добавить мем в пул"),
    BotCommand(command="memes", description="Листалка по пулу"),
    BotCommand(command="delmeme", description="Удалить мем по номеру"),
    BotCommand(command="settext", description="Текст приветствия"),
    BotCommand(command="triggers", description="Слова-триггеры"),
    BotCommand(command="addtrigger", description="Добавить триггер"),
    BotCommand(command="deltrigger", description="Убрать триггер"),
    BotCommand(command="cooldown", description="Пауза между ответами"),
    BotCommand(command="on", description="Включить автоответы"),
    BotCommand(command="off", description="Выключить автоответы"),
    BotCommand(command="stats", description="Статистика"),
]


async def setup_commands(bot: Bot, admin_ids: frozenset[int]) -> set[int]:
    """Всем — две команды, админам в их личке — полный список.

    Возвращает id админов, которым меню уже доставлено; остальным его поставит
    AdminMenuMiddleware, когда они впервые напишут боту.
    """
    await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
    done: set[int] = set()
    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(
                ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except TelegramAPIError as exc:
            # Обычная причина: админ ещё ни разу не написал боту.
            logger.info(
                "Меню админу %s поставлю, когда он напишет боту (%s)", admin_id, exc
            )
        else:
            done.add(admin_id)
    return done


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config()

    db = Database(config.db_path)
    await db.connect()

    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp["db"] = db
    dp["admin_ids"] = config.admin_ids
    # Админ-роутер первым: его команды не должны попадать в матчинг триггеров.
    dp.include_router(admin.router)
    dp.include_router(greeting.router)

    try:
        me = await bot.get_me()
        logger.info("Запускаюсь как @%s (id %s)", me.username, me.id)
        if not config.admin_ids:
            logger.warning(
                "ADMIN_IDS пуст — админ-команды недоступны никому. "
                "Узнай свой ID у @userinfobot и впиши его в .env"
            )
        menu_done = await setup_commands(bot, config.admin_ids)
        # Именно outer: обычный middleware сработал бы только на сообщениях,
        # которые дошли до хендлера, а меню нужно ставить на любом первом.
        dp.message.outer_middleware(
            AdminMenuMiddleware(config.admin_ids, ADMIN_COMMANDS, menu_done)
        )
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()
        logger.info("Остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigError as exc:
        raise SystemExit(f"Ошибка конфигурации: {exc}")
    except KeyboardInterrupt:
        pass
