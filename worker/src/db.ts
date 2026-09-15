/** Слой доступа к D1. Повторяет bot/db.py из Python-версии. */

export interface Meme {
  id: number;
  file_id: string;
  file_unique_id: string;
  kind: string;
  caption: string | null;
  added_by: number | null;
  added_at: string;
  broken: number;
}

export interface Stats {
  memes: number;
  broken: number;
  triggers: number;
  greets_total: number;
  greets_day: number;
  chats: number;
  users: number;
}

const DEFAULTS: Record<string, string> = {
  greeting_text: "Привет, {name}! 👋",
  enabled: "1",
  cooldown_minutes: "360",
};

export class Db {
  constructor(private readonly d1: D1Database) {}

  private async scalar(sql: string, ...args: unknown[]): Promise<number> {
    const row = await this.d1
      .prepare(sql)
      .bind(...args)
      .first<Record<string, number>>();
    if (!row) return 0;
    const first = Object.values(row)[0];
    return typeof first === "number" ? first : 0;
  }

  // --- настройки ---------------------------------------------------------

  async getSetting(key: string): Promise<string> {
    const row = await this.d1
      .prepare("SELECT value FROM settings WHERE key = ?")
      .bind(key)
      .first<{ value: string }>();
    return row?.value ?? DEFAULTS[key] ?? "";
  }

  async setSetting(key: string, value: string): Promise<void> {
    await this.d1
      .prepare(
        "INSERT INTO settings (key, value) VALUES (?, ?) " +
          "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
      )
      .bind(key, value)
      .run();
  }

  async isEnabled(): Promise<boolean> {
    return (await this.getSetting("enabled")) === "1";
  }

  async setEnabled(value: boolean): Promise<void> {
    await this.setSetting("enabled", value ? "1" : "0");
  }

  async greetingText(): Promise<string> {
    return this.getSetting("greeting_text");
  }

  async cooldownMinutes(): Promise<number> {
    const parsed = Number.parseInt(await this.getSetting("cooldown_minutes"), 10);
    return Number.isNaN(parsed) ? 360 : parsed;
  }

  // --- мемы --------------------------------------------------------------

  /** Возвращает id нового мема, либо null если такой уже есть. */
  async addMeme(
    fileId: string,
    fileUniqueId: string,
    kind: string,
    caption: string | null,
    addedBy: number | null,
  ): Promise<number | null> {
    const res = await this.d1
      .prepare(
        "INSERT OR IGNORE INTO memes (file_id, file_unique_id, kind, caption, added_by) " +
          "VALUES (?, ?, ?, ?, ?)",
      )
      .bind(fileId, fileUniqueId, kind, caption, addedBy)
      .run();
    // changes = 0 значит сработал OR IGNORE, то есть file_unique_id уже в пуле.
    return res.meta.changes === 0 ? null : res.meta.last_row_id;
  }

  async deleteMeme(id: number): Promise<boolean> {
    const res = await this.d1.prepare("DELETE FROM memes WHERE id = ?").bind(id).run();
    return res.meta.changes > 0;
  }

  async markBroken(id: number): Promise<void> {
    await this.d1.prepare("UPDATE memes SET broken = 1 WHERE id = ?").bind(id).run();
  }

  async countMemes(): Promise<number> {
    return this.scalar("SELECT COUNT(*) AS n FROM memes WHERE broken = 0");
  }

  async memeAt(offset: number): Promise<Meme | null> {
    return this.d1
      .prepare("SELECT * FROM memes WHERE broken = 0 ORDER BY id LIMIT 1 OFFSET ?")
      .bind(Math.max(offset, 0))
      .first<Meme>();
  }

  /** Случайный живой мем, по возможности не тот же, что был в прошлый раз. */
  async pickMeme(chatId: number): Promise<Meme | null> {
    const fresh = await this.d1
      .prepare(
        "SELECT * FROM memes WHERE broken = 0 AND id != " +
          "COALESCE((SELECT meme_id FROM last_meme WHERE chat_id = ?), -1) " +
          "ORDER BY RANDOM() LIMIT 1",
      )
      .bind(chatId)
      .first<Meme>();
    if (fresh) return fresh;
    // В пуле остался ровно один мем — лучше повторить его, чем промолчать.
    return this.d1
      .prepare("SELECT * FROM memes WHERE broken = 0 ORDER BY RANDOM() LIMIT 1")
      .first<Meme>();
  }

  async setLastMeme(chatId: number, memeId: number): Promise<void> {
    await this.d1
      .prepare(
        "INSERT INTO last_meme (chat_id, meme_id) VALUES (?, ?) " +
          "ON CONFLICT(chat_id) DO UPDATE SET meme_id = excluded.meme_id",
      )
      .bind(chatId, memeId)
      .run();
  }

  // --- триггеры ----------------------------------------------------------

  async listTriggers(): Promise<string[]> {
    const res = await this.d1
      .prepare("SELECT phrase FROM triggers ORDER BY phrase")
      .all<{ phrase: string }>();
    return res.results.map((r) => r.phrase);
  }

  async addTrigger(phrase: string): Promise<boolean> {
    const res = await this.d1
      .prepare("INSERT OR IGNORE INTO triggers (phrase) VALUES (?)")
      .bind(phrase.trim().toLowerCase())
      .run();
    return res.meta.changes > 0;
  }

  async deleteTrigger(phrase: string): Promise<boolean> {
    const res = await this.d1
      .prepare("DELETE FROM triggers WHERE phrase = ?")
      .bind(phrase.trim().toLowerCase())
      .run();
    return res.meta.changes > 0;
  }

  // --- кулдаун и статистика ---------------------------------------------

  async canGreet(chatId: number, userId: number, cooldownMinutes: number): Promise<boolean> {
    if (cooldownMinutes <= 0) return true;
    const row = await this.d1
      .prepare(
        "SELECT 1 AS hit FROM greet_log WHERE chat_id = ? AND user_id = ? " +
          "AND ts > datetime('now', ?) LIMIT 1",
      )
      .bind(chatId, userId, `-${cooldownMinutes} minutes`)
      .first();
    return row === null;
  }

  async logGreet(chatId: number, userId: number, memeId: number | null): Promise<void> {
    await this.d1
      .prepare("INSERT INTO greet_log (chat_id, user_id, meme_id) VALUES (?, ?, ?)")
      .bind(chatId, userId, memeId)
      .run();
  }

  async stats(): Promise<Stats> {
    return {
      memes: await this.countMemes(),
      broken: await this.scalar("SELECT COUNT(*) AS n FROM memes WHERE broken = 1"),
      triggers: await this.scalar("SELECT COUNT(*) AS n FROM triggers"),
      greets_total: await this.scalar("SELECT COUNT(*) AS n FROM greet_log"),
      greets_day: await this.scalar(
        "SELECT COUNT(*) AS n FROM greet_log WHERE ts > datetime('now', '-1 day')",
      ),
      chats: await this.scalar("SELECT COUNT(DISTINCT chat_id) AS n FROM greet_log"),
      users: await this.scalar("SELECT COUNT(DISTINCT user_id) AS n FROM greet_log"),
    };
  }
}
