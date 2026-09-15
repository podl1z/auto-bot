/**
 * Точка входа Cloudflare Worker.
 *
 * Отличие от Python-версии: воркер не живёт постоянно и не может сам опрашивать
 * Telegram (long polling). Здесь наоборот — Telegram POST-ит апдейты на /webhook,
 * воркер просыпается, отвечает и умирает.
 */
import { Bot, webhookCallback } from "grammy";
import { adminComposer } from "./admin";
import { Db } from "./db";
import { greetingComposer } from "./greeting";
import type { BotContext, Env } from "./types";

const PUBLIC_COMMANDS = [
  { command: "start", description: "Мемчик и привет" },
  { command: "help", description: "Что я умею" },
];

const ADMIN_COMMANDS = [
  ...PUBLIC_COMMANDS,
  { command: "addmeme", description: "Добавить мем в пул" },
  { command: "memes", description: "Листалка по пулу" },
  { command: "delmeme", description: "Удалить мем по номеру" },
  { command: "settext", description: "Текст приветствия" },
  { command: "triggers", description: "Слова-триггеры" },
  { command: "addtrigger", description: "Добавить триггер" },
  { command: "deltrigger", description: "Убрать триггер" },
  { command: "cooldown", description: "Пауза между ответами" },
  { command: "on", description: "Включить автоответы" },
  { command: "off", description: "Выключить автоответы" },
  { command: "stats", description: "Статистика" },
];

export function parseAdminIds(raw: string): Set<number> {
  const ids = (raw ?? "")
    .split(/[,\s;]+/)
    .filter(Boolean)
    .map((p) => Number.parseInt(p, 10))
    .filter((n) => Number.isFinite(n));
  return new Set(ids);
}

function createBot(env: Env): Bot<BotContext> {
  const bot = new Bot<BotContext>(env.BOT_TOKEN);
  const db = new Db(env.DB);
  const adminIds = parseAdminIds(env.ADMIN_IDS);

  bot.use(async (ctx, next) => {
    ctx.db = db;
    ctx.adminIds = adminIds;
    await next();
  });

  // Доставляем админу меню команд при первом его сообщении: на setWebhook
  // Telegram отвечает «chat not found», если админ ещё не писал боту.
  // Флаг держим в D1, а не в памяти — воркер между запросами не живёт.
  bot.use(async (ctx, next) => {
    const id = ctx.from?.id;
    if (id !== undefined && adminIds.has(id)) {
      const key = `menu_done_${id}`;
      if ((await db.getSetting(key)) !== "1") {
        try {
          await ctx.api.setMyCommands(ADMIN_COMMANDS, {
            scope: { type: "chat", chat_id: id },
          });
          await db.setSetting(key, "1");
        } catch (err) {
          console.debug(`Меню для админа ${id} пока не ставится: ${String(err)}`);
        }
      }
    }
    await next();
  });

  bot.use(adminComposer);
  bot.use(greetingComposer);

  bot.catch((err) => console.error("Ошибка в хендлере:", err));
  return bot;
}

/** Разовая настройка: прописывает вебхук на самого себя и меню команд. */
async function handleSetup(url: URL, env: Env): Promise<Response> {
  const bot = createBot(env);
  await bot.init();

  const hookUrl = `${url.origin}/webhook`;
  await bot.api.setWebhook(hookUrl, {
    secret_token: env.WEBHOOK_SECRET,
    drop_pending_updates: true,
  });
  await bot.api.setMyCommands(PUBLIC_COMMANDS);

  const menu: Record<string, string> = {};
  for (const id of parseAdminIds(env.ADMIN_IDS)) {
    try {
      await bot.api.setMyCommands(ADMIN_COMMANDS, {
        scope: { type: "chat", chat_id: id },
      });
      menu[id] = "меню поставлено";
    } catch {
      menu[id] = "поставится, когда админ напишет боту";
    }
  }

  return Response.json({
    ok: true,
    bot: bot.botInfo.username,
    webhook: hookUrl,
    admins: menu,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/webhook") {
      // Telegram присылает секрет в заголовке — так мы знаем, что запрос от него,
      // а не от случайного человека, который узнал адрес воркера.
      if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
        return new Response("Forbidden", { status: 403 });
      }
      return webhookCallback(createBot(env), "cloudflare-mod")(request);
    }

    if (url.pathname === "/setup") {
      if (url.searchParams.get("secret") !== env.WEBHOOK_SECRET) {
        return new Response("Forbidden", { status: 403 });
      }
      return handleSetup(url, env);
    }

    return new Response(
      "auto-bot жив.\nВебхук: POST /webhook\nНастройка: GET /setup?secret=...",
      { headers: { "content-type": "text/plain; charset=utf-8" } },
    );
  },
};
