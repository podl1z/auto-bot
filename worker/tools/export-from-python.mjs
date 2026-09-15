/**
 * Переносит мемы и настройки из SQLite Python-версии в SQL-файл для D1.
 *
 * Запуск:  node tools/export-from-python.mjs
 * Потом:   npx wrangler d1 execute auto-bot --remote --file=migrate.sql
 */
import { DatabaseSync } from "node:sqlite";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = process.argv[2] ?? resolve(here, "../../data/bot.db");
const out = resolve(here, "../migrate.sql");

const q = (v) =>
  v === null || v === undefined ? "NULL" : `'${String(v).replaceAll("'", "''")}'`;

const db = new DatabaseSync(src, { readOnly: true });
const lines = ["-- Сгенерировано tools/export-from-python.mjs", ""];

const memes = db.prepare("SELECT * FROM memes WHERE broken = 0").all();
for (const m of memes) {
  lines.push(
    "INSERT OR IGNORE INTO memes (file_id, file_unique_id, kind, caption, added_by) VALUES (" +
      [m.file_id, m.file_unique_id, m.kind, m.caption, m.added_by].map(q).join(", ") +
      ");",
  );
}

const settings = db.prepare("SELECT * FROM settings").all();
for (const s of settings) {
  lines.push(
    `INSERT INTO settings (key, value) VALUES (${q(s.key)}, ${q(s.value)}) ` +
      "ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
  );
}

const triggers = db.prepare("SELECT phrase FROM triggers").all();
for (const t of triggers) {
  lines.push(`INSERT OR IGNORE INTO triggers (phrase) VALUES (${q(t.phrase)});`);
}

db.close();
writeFileSync(out, lines.join("\n") + "\n", "utf8");
console.log(`Мемов: ${memes.length}, настроек: ${settings.length}, триггеров: ${triggers.length}`);
console.log(`Записал: ${out}`);
console.log("Дальше: npx wrangler d1 execute auto-bot --remote --file=migrate.sql");
