"""Загрузка и валидация настроек из .env."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Конфиг заполнен неправильно — запускаться нет смысла."""


@dataclass(frozen=True)
class Config:
    token: str
    admin_ids: frozenset[int]
    db_path: Path


def _parse_admin_ids(raw: str) -> frozenset[int]:
    parts = [p for p in re.split(r"[,\s;]+", raw.strip()) if p]
    ids = set()
    for part in parts:
        try:
            ids.add(int(part))
        except ValueError:
            raise ConfigError(
                f"ADMIN_IDS содержит не число: {part!r}. "
                "Нужны числовые ID через запятую, например: 12345678,87654321"
            ) from None
    return frozenset(ids)


def load_config() -> Config:
    load_dotenv(BASE_DIR / ".env")

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or "ЗАМЕНИ" in token.upper() or token.startswith("123456789:"):
        raise ConfigError(
            "BOT_TOKEN не задан. Скопируй .env.example в .env и вставь токен от @BotFather."
        )

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

    db_raw = os.getenv("DB_PATH", "data/bot.db").strip() or "data/bot.db"
    db_path = Path(db_raw)
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    return Config(token=token, admin_ids=admin_ids, db_path=db_path)
