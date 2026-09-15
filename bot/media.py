"""Разбор и отправка медиа. Мемы храним как file_id Телеграма, файлы не качаем."""
from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import Message

# Порядок важен: у гифки заполнены и animation, и document,
# у видеокружка — и video_note, и video. Проверяем от частного к общему.
KINDS = ("animation", "video_note", "video", "sticker", "photo", "voice", "document")

# Этим методам Telegram не даёт подпись.
WITHOUT_CAPTION = {"sticker", "video_note"}

HUMAN_KIND = {
    "photo": "фото",
    "animation": "гифка",
    "video": "видео",
    "video_note": "кружок",
    "sticker": "стикер",
    "voice": "голосовое",
    "document": "файл",
}


@dataclass(frozen=True)
class Media:
    file_id: str
    file_unique_id: str
    kind: str
    caption: str | None


def extract_media(message: Message) -> Media | None:
    """Достаёт медиа из сообщения. Для фото берёт самый крупный размер."""
    for kind in KINDS:
        value = getattr(message, kind, None)
        if not value:
            continue
        item = value[-1] if kind == "photo" else value
        return Media(
            file_id=item.file_id,
            file_unique_id=item.file_unique_id,
            kind=kind,
            caption=message.caption,
        )
    return None


async def send_media(
    message: Message,
    file_id: str,
    kind: str,
    caption: str | None = None,
    **kwargs: object,
) -> Message:
    """Отправляет медиа в чат сообщения методом, подходящим под его тип."""
    sender = getattr(message, f"answer_{kind}", None)
    if sender is None:
        sender = message.answer_document
    if kind in WITHOUT_CAPTION:
        return await sender(file_id, **kwargs)
    return await sender(file_id, caption=caption, **kwargs)
