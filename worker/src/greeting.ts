/** Основная логика: на /start и на слова-триггеры — мем плюс привет. */
import { Composer, GrammyError } from "grammy";
import type { BotContext } from "./types";
import { sendMedia } from "./media";
import { matchesTrigger } from "./triggers";

// Сколько битых file_id подряд готовы пережить, прежде чем ответить без мема.
const MAX_MEME_ATTEMPTS = 5;

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Подставляет {name} и {mention} в шаблон приветствия. */
export function renderGreeting(
  template: string,
  userId: number,
  firstName: string,
): string {
  const name = escapeHtml(firstName || "друг");
  const mention = `<a href="tg://user?id=${userId}">${name}</a>`;
  return template.split("{name}").join(name).split("{mention}").join(mention);
}

/** Шлёт случайный мем. Битые file_id помечает и пробует следующий. */
async function sendRandomMeme(ctx: BotContext): Promise<number | null> {
  const chatId = ctx.chat?.id;
  if (chatId === undefined) return null;

  for (let attempt = 0; attempt < MAX_MEME_ATTEMPTS; attempt++) {
    const meme = await ctx.db.pickMeme(chatId);
    if (!meme) return null;
    try {
      await sendMedia(ctx, meme.file_id, meme.kind, meme.caption);
    } catch (err) {
      if (!(err instanceof GrammyError)) throw err;
      console.warn(`Мем #${meme.id} не отправился (${err.description}), помечаю битым`);
      await ctx.db.markBroken(meme.id);
      continue;
    }
    await ctx.db.setLastMeme(chatId, meme.id);
    return meme.id;
  }
  return null;
}

export async function greet(ctx: BotContext): Promise<void> {
  const user = ctx.from;
  const chatId = ctx.chat?.id;
  if (!user || user.is_bot || chatId === undefined) return;

  if (!(await ctx.db.isEnabled())) return;

  const cooldown = await ctx.db.cooldownMinutes();
  if (!(await ctx.db.canGreet(chatId, user.id, cooldown))) return;

  const memeId = await sendRandomMeme(ctx);

  const text = renderGreeting(await ctx.db.greetingText(), user.id, user.first_name);
  try {
    await ctx.reply(text, { parse_mode: "HTML" });
  } catch (err) {
    if (!(err instanceof GrammyError)) throw err;
    // Кривая разметка в шаблоне — отправляем как есть, без HTML.
    console.warn("Приветствие не разобралось как HTML, шлю текстом");
    await ctx.reply(text);
  }

  await ctx.db.logGreet(chatId, user.id, memeId);

  if (memeId === null && ctx.adminIds.has(user.id) && (await ctx.db.countMemes()) === 0) {
    await ctx.reply(
      "☝️ Пул мемов пуст. Кинь мне картинку с подписью <code>/addmeme</code> " +
        "или ответь на неё этой командой.",
      { parse_mode: "HTML" },
    );
  }
}

export const greetingComposer = new Composer<BotContext>();

greetingComposer.command("start", greet);

greetingComposer.on("message", async (ctx, next) => {
  const text = ctx.message.text ?? ctx.message.caption ?? "";
  if (!text || text.startsWith("/")) return next();
  if (matchesTrigger(text, await ctx.db.listTriggers())) {
    await greet(ctx);
    return;
  }
  return next();
});
