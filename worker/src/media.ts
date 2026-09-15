/** Разбор и отправка медиа. Порт bot/media.py. */
import type { Context, InlineKeyboard } from "grammy";
import type { Message } from "grammy/types";

export type Kind =
  | "animation"
  | "video_note"
  | "video"
  | "sticker"
  | "photo"
  | "voice"
  | "document";

export const HUMAN_KIND: Record<Kind, string> = {
  photo: "фото",
  animation: "гифка",
  video: "видео",
  video_note: "кружок",
  sticker: "стикер",
  voice: "голосовое",
  document: "файл",
};

export interface Media {
  fileId: string;
  fileUniqueId: string;
  kind: Kind;
  caption: string | null;
}

function build(
  file: { file_id: string; file_unique_id: string },
  kind: Kind,
  caption: string | null,
): Media {
  return {
    fileId: file.file_id,
    fileUniqueId: file.file_unique_id,
    kind,
    caption,
  };
}

/**
 * Достаёт медиа из сообщения. Для фото берёт самый крупный размер.
 *
 * Порядок проверок важен: у гифки заполнены и animation, и document,
 * у видеокружка — и video_note, и video. Идём от частного к общему.
 */
export function extractMedia(msg: Message | undefined): Media | null {
  if (!msg) return null;
  const caption = msg.caption ?? null;

  if (msg.animation) return build(msg.animation, "animation", caption);
  if (msg.video_note) return build(msg.video_note, "video_note", caption);
  if (msg.video) return build(msg.video, "video", caption);
  if (msg.sticker) return build(msg.sticker, "sticker", caption);
  if (msg.photo?.length) {
    const largest = msg.photo[msg.photo.length - 1];
    if (largest) return build(largest, "photo", caption);
  }
  if (msg.voice) return build(msg.voice, "voice", caption);
  if (msg.document) return build(msg.document, "document", caption);

  return null;
}

export interface SendOptions {
  reply_markup?: InlineKeyboard;
}

/**
 * Отправляет медиа методом, подходящим под его тип.
 * Стикерам и кружкам Telegram не даёт подпись, поэтому caption им не передаём.
 */
export async function sendMedia(
  ctx: Context,
  fileId: string,
  kind: string,
  caption: string | null,
  options: SendOptions = {},
): Promise<void> {
  const full = caption ? { ...options, caption } : options;
  switch (kind) {
    case "photo":
      await ctx.replyWithPhoto(fileId, full);
      return;
    case "animation":
      await ctx.replyWithAnimation(fileId, full);
      return;
    case "video":
      await ctx.replyWithVideo(fileId, full);
      return;
    case "voice":
      await ctx.replyWithVoice(fileId, full);
      return;
    case "sticker":
      await ctx.replyWithSticker(fileId, options);
      return;
    case "video_note":
      await ctx.replyWithVideoNote(fileId, options);
      return;
    default:
      await ctx.replyWithDocument(fileId, full);
  }
}
