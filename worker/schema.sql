-- Схема D1. Повторяет SQLite-схему Python-версии (bot/db.py).
-- Накатывается командой: npm run db:remote

CREATE TABLE IF NOT EXISTS memes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id         TEXT    NOT NULL,
    file_unique_id  TEXT    NOT NULL UNIQUE,
    kind            TEXT    NOT NULL,
    caption         TEXT,
    added_by        INTEGER,
    added_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    broken          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS triggers (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS greet_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    meme_id  INTEGER,
    ts       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_greet_lookup ON greet_log (chat_id, user_id, ts);

CREATE TABLE IF NOT EXISTS last_meme (
    chat_id  INTEGER PRIMARY KEY,
    meme_id  INTEGER NOT NULL
);

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('greeting_text', 'Привет, {name}! 👋'),
    ('enabled', '1'),
    ('cooldown_minutes', '360');

INSERT OR IGNORE INTO triggers (phrase) VALUES ('старт'), ('start'), ('привет');
