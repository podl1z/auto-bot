"""Мидлвари."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, Message

logger = logging.getLogger(__name__)


class AdminMenuMiddleware(BaseMiddleware):
    """Доставляет админу меню команд при первом же его сообщении.

    На старте бот не может поставить персональное меню админу, который ещё ни
    разу ему не писал: Telegram отвечает «chat not found». Тогда админ видит в
    списке команд только /start и /help. Здесь делаем вторую попытку — в момент,
    когда личный чат заведомо существует, потому что админ только что написал.
    """

    def __init__(
        self,
        admin_ids: frozenset[int],
        commands: list[BotCommand],
        already_done: set[int] | None = None,
    ) -> None:
        self._admin_ids = admin_ids
        self._commands = commands
        self._done: set[int] = already_done or set()

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user is not None and user.id in self._admin_ids and user.id not in self._done:
            try:
                await data["bot"].set_my_commands(
                    self._commands, scope=BotCommandScopeChat(chat_id=user.id)
                )
            except TelegramAPIError as exc:
                # Админ написал из группы, а в личку боту ещё не заходил — ждём.
                logger.debug("Меню для админа %s пока не ставится: %s", user.id, exc)
            else:
                self._done.add(user.id)
                logger.info("Поставил меню команд админу %s", user.id)

        return await handler(event, data)
