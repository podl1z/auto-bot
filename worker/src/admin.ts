/** Админ-команды. Порт bot/handlers/admin.py. */
import { Composer, GrammyError, InlineKeyboard } from "grammy";
import type { BotContext } from "./types";
import { HUMAN_KIND, extractMedia, sendMedia, type Kind } from "./media";
import { renderGreeting } from "./greeting";

const PUBLIC_HELP = "Привет! Напиши мне <b>/start</b> — и я кину мемчик. 🙂";

const ADMIN_HELP = `<b>Команды админа</b>

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

Триггеры в группах работают, только если в @BotFather выключен Group Privacy.`;

const HTML = { parse_mode: "HTML" } as const;

export const adminComposer = new Composer<BotContext>();

// /help доступна всем: админу — полный список, остальным короткая справка.
adminComposer.command("help", async (ctx) => {
  const isAdmin = ctx.from !== undefined && ctx.adminIds.has(ctx.from.id);
  await ctx.reply(isAdmin ? ADMIN_HELP : PUBLIC_HELP, HTML);
});

// Всё, что ниже, — только для админов из ADMIN_IDS.
const admin = adminComposer.filter(
  (ctx): boolean => ctx.from !== undefined && ctx.adminIds.has(ctx.from.id),
);

function navKeyboard(memeId: number, offset: number, total: number): InlineKeyboard {
  return new InlineKeyboard()
    .text("◀️", `mnav:go:${offset - 1}`)
    .text(`#${memeId} · ${offset + 1}/${total}`, `mnav:noop:${offset}`)
    .text("▶️", `mnav:go:${offset + 1}`)
    .row()
    .text("🗑 Удалить", `mnav:del:${offset}`);
}

/**
 * Показывает один мем из пула с кнопками навигации.
 *
 * Номер и позиция живут в подписи к средней кнопке, а не в caption:
 * у стикеров и кружков подписи нет, а клавиатура есть у всех типов.
 */
async function showMeme(ctx: BotContext, offset: number): Promise<void> {
  const total = await ctx.db.countMemes();
  if (total === 0) {
    await ctx.reply("Пул пуст. Кинь мне картинку с подписью /addmeme.");
    return;
  }

  const wrapped = ((offset % total) + total) % total;
  const meme = await ctx.db.memeAt(wrapped);
  if (!meme) {
    await ctx.reply("Не нашёл мем на этой позиции, попробуй /memes заново.");
    return;
  }

  try {
    await sendMedia(ctx, meme.file_id, meme.kind, meme.caption, {
      reply_markup: navKeyboard(meme.id, wrapped, total),
    });
  } catch (err) {
    if (!(err instanceof GrammyError)) throw err;
    console.warn(`Мем #${meme.id} не показался: ${err.description}`);
    await ctx.db.markBroken(meme.id);
    await ctx.reply(
      `Мем #${meme.id} не открывается, пометил битым. Полистай дальше: /memes`,
    );
  }
}

admin.command("addmeme", async (ctx) => {
  const args = (ctx.match ?? "").trim();
  const replied = ctx.message?.reply_to_message;

  // Если медиа прислали с подписью «/addmeme ...», сама команда в подписи не нужна.
  const source = replied ?? ctx.message;
  const caption = replied ? args || replied.caption || null : args || null;

  const media = extractMedia(source);
  if (!media) {
    await ctx.reply(
      "Не вижу медиа. Ответь командой на картинку, гифку, видео или стикер — " +
        "либо пришли медиа, подписав его <code>/addmeme</code>.",
      HTML,
    );
    return;
  }

  const memeId = await ctx.db.addMeme(
    media.fileId,
    media.fileUniqueId,
    media.kind,
    caption,
    ctx.from?.id ?? null,
  );
  if (memeId === null) {
    await ctx.reply("Этот мем уже есть в пуле. 🤷");
    return;
  }

  const kind = HUMAN_KIND[media.kind as Kind] ?? media.kind;
  await ctx.reply(
    `✅ Добавил ${kind} как мем #${memeId}. Всего в пуле: ${await ctx.db.countMemes()}.`,
  );
});

admin.command("memes", async (ctx) => {
  await showMeme(ctx, 0);
});

admin.callbackQuery(/^mnav:(go|del|noop):(-?\d+)$/, async (ctx) => {
  const action = ctx.match?.[1];
  const offset = Number.parseInt(ctx.match?.[2] ?? "0", 10);

  if (action === "noop") {
    await ctx.answerCallbackQuery();
    return;
  }

  if (action === "del") {
    const meme = await ctx.db.memeAt(offset);
    if (meme && (await ctx.db.deleteMeme(meme.id))) {
      await ctx.answerCallbackQuery(`Мем #${meme.id} удалён`);
    } else {
      await ctx.answerCallbackQuery("Уже удалён");
    }
  }

  // Медиа разных типов друг в друга не редактируются — проще удалить и прислать заново.
  try {
    await ctx.deleteMessage();
  } catch {
    console.debug("Не смог удалить сообщение листалки, шлю новое");
  }

  await showMeme(ctx, offset);
  if (action !== "del") await ctx.answerCallbackQuery();
});

admin.command("delmeme", async (ctx) => {
  const raw = (ctx.match ?? "").trim().replace(/^#/, "");
  if (!/^\d+$/.test(raw)) {
    await ctx.reply("Формат: <code>/delmeme 12</code>. Номера видно в /memes.", HTML);
    return;
  }
  if (await ctx.db.deleteMeme(Number.parseInt(raw, 10))) {
    await ctx.reply(`🗑 Мем #${raw} удалён. В пуле: ${await ctx.db.countMemes()}.`);
  } else {
    await ctx.reply(`Мема #${raw} нет в пуле.`);
  }
});

admin.command("settext", async (ctx) => {
  const text = (ctx.match ?? "").trim();
  if (!text) {
    const current = await ctx.db.greetingText();
    await ctx.reply(
      "Сейчас приветствие такое:\n\n" +
        `<code>${current.replace(/</g, "&lt;")}</code>\n\n` +
        "Поменять: <code>/settext Дарова, {name}!</code>",
      HTML,
    );
    return;
  }

  const user = ctx.from;
  if (!user) return;

  // Проверяем разметку до сохранения: если HTML кривой, Telegram не примет
  // сообщение — и лучше об этом узнать сейчас, а не на первом же госте.
  try {
    await ctx.reply("Так это будет выглядеть:");
    await ctx.reply(renderGreeting(text, user.id, user.first_name), HTML);
  } catch (err) {
    if (!(err instanceof GrammyError)) throw err;
    await ctx.reply(
      `Не сохранил — Telegram не принял разметку: ${err.description}\n` +
        "Старое приветствие осталось на месте.",
    );
    return;
  }

  await ctx.db.setSetting("greeting_text", text);
  await ctx.reply("✅ Сохранил.");
});

admin.command("triggers", async (ctx) => {
  const phrases = await ctx.db.listTriggers();
  if (phrases.length === 0) {
    await ctx.reply(
      "Триггеров нет — бот отвечает только на /start.\n" +
        "Добавить: <code>/addtrigger старт</code>",
      HTML,
    );
    return;
  }
  await ctx.reply(
    `<b>Слова-триггеры</b>\n${phrases.map((p) => `• ${p}`).join("\n")}\n\n` +
      "В группах они работают только при выключенном Group Privacy.",
    HTML,
  );
});

admin.command("addtrigger", async (ctx) => {
  const phrase = (ctx.match ?? "").trim().toLowerCase();
  if (!phrase) {
    await ctx.reply("Формат: <code>/addtrigger старт</code>", HTML);
    return;
  }
  await ctx.reply(
    (await ctx.db.addTrigger(phrase))
      ? `✅ Теперь реагирую на «${phrase}».`
      : `«${phrase}» уже в списке.`,
  );
});

admin.command("deltrigger", async (ctx) => {
  const phrase = (ctx.match ?? "").trim().toLowerCase();
  if (!phrase) {
    await ctx.reply("Формат: <code>/deltrigger старт</code>", HTML);
    return;
  }
  await ctx.reply(
    (await ctx.db.deleteTrigger(phrase))
      ? `🗑 Убрал «${phrase}».`
      : `«${phrase}» и так не было.`,
  );
});

admin.command("cooldown", async (ctx) => {
  const raw = (ctx.match ?? "").trim();
  if (!raw) {
    await ctx.reply(
      `Сейчас пауза: <b>${await ctx.db.cooldownMinutes()}</b> мин.\n` +
        "Поменять: <code>/cooldown 60</code>. Ноль — отвечать всегда.",
      HTML,
    );
    return;
  }
  if (!/^\d+$/.test(raw)) {
    await ctx.reply("Нужно целое число минут, например: <code>/cooldown 60</code>", HTML);
    return;
  }

  const minutes = Number.parseInt(raw, 10);
  await ctx.db.setSetting("cooldown_minutes", String(minutes));
  await ctx.reply(
    minutes === 0
      ? "✅ Пауза убрана — отвечаю на каждый /start."
      : `✅ Одному человеку в одном чате отвечаю не чаще раза в ${minutes} мин.`,
  );
});

admin.command("on", async (ctx) => {
  await ctx.db.setEnabled(true);
  await ctx.reply("🟢 Автоответы включены.");
});

admin.command("off", async (ctx) => {
  await ctx.db.setEnabled(false);
  await ctx.reply("🔴 Автоответы выключены. Вернуть: /on");
});

admin.command("stats", async (ctx) => {
  const s = await ctx.db.stats();
  const enabled = (await ctx.db.isEnabled()) ? "🟢 включены" : "🔴 выключены";
  const broken = s.broken ? `\nБитых мемов: ${s.broken}` : "";
  await ctx.reply(
    "<b>Статистика</b>\n" +
      `Автоответы: ${enabled}\n` +
      `Мемов в пуле: ${s.memes}${broken}\n` +
      `Триггеров: ${s.triggers}\n` +
      `Пауза: ${await ctx.db.cooldownMinutes()} мин\n\n` +
      `Ответов за сутки: ${s.greets_day}\n` +
      `Ответов всего: ${s.greets_total}\n` +
      `Чатов: ${s.chats} · людей: ${s.users}`,
    HTML,
  );
});
