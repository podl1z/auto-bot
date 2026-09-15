import type { Context } from "grammy";
import type { Db } from "./db";

/** Контекст с прокинутыми зависимостями — аналог workflow_data в aiogram. */
export type BotContext = Context & {
  db: Db;
  adminIds: Set<number>;
};

export interface Env {
  DB: D1Database;
  BOT_TOKEN: string;
  ADMIN_IDS: string;
  WEBHOOK_SECRET: string;
}
