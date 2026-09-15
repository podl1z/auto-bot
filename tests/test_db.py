import pytest
import pytest_asyncio

from bot.db import Database

CHAT = -100123
USER = 777


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


async def add(database, n: int) -> int:
    meme_id = await database.add_meme(f"file{n}", f"uniq{n}", "photo", None, USER)
    assert meme_id is not None
    return meme_id


async def test_дефолты_проставились(db):
    assert await db.is_enabled()
    assert await db.cooldown_minutes() == 360
    assert "старт" in await db.list_triggers()


async def test_добавление_мема(db):
    meme_id = await add(db, 1)
    assert meme_id > 0
    assert await db.count_memes() == 1


async def test_дубль_не_добавляется(db):
    await add(db, 1)
    assert await db.add_meme("другой_file_id", "uniq1", "photo", None, USER) is None
    assert await db.count_memes() == 1


async def test_удаление_мема(db):
    meme_id = await add(db, 1)
    assert await db.delete_meme(meme_id) is True
    assert await db.delete_meme(meme_id) is False
    assert await db.count_memes() == 0


async def test_битые_мемы_не_выдаются(db):
    meme_id = await add(db, 1)
    await db.mark_broken(meme_id)
    assert await db.count_memes() == 0
    assert await db.pick_meme(CHAT) is None


async def test_кулдаун(db):
    assert await db.can_greet(CHAT, USER, 60) is True
    await db.log_greet(CHAT, USER, None)

    assert await db.can_greet(CHAT, USER, 60) is False
    # нулевая пауза пускает всегда
    assert await db.can_greet(CHAT, USER, 0) is True
    # другой человек и другой чат считаются отдельно
    assert await db.can_greet(CHAT, USER + 1, 60) is True
    assert await db.can_greet(CHAT + 1, USER, 60) is True


async def test_мем_не_повторяется_подряд(db):
    first = await add(db, 1)
    second = await add(db, 2)

    await db.set_last_meme(CHAT, first)
    for _ in range(10):
        picked = await db.pick_meme(CHAT)
        assert picked["id"] == second


async def test_единственный_мем_выдаётся_снова(db):
    """Если в пуле один мем, лучше повторить его, чем промолчать."""
    only = await add(db, 1)
    await db.set_last_meme(CHAT, only)
    picked = await db.pick_meme(CHAT)
    assert picked is not None and picked["id"] == only


async def test_триггеры(db):
    assert await db.add_trigger("Го") is True
    assert "го" in await db.list_triggers(), "фраза должна лечь в нижнем регистре"
    assert await db.add_trigger("го") is False
    assert await db.delete_trigger("го") is True
    assert await db.delete_trigger("го") is False


async def test_настройки_переживают_переоткрытие(db, tmp_path):
    await db.set_setting("greeting_text", "Здорова, {name}")
    await db.set_enabled(False)
    await db.close()

    again = Database(tmp_path / "test.db")
    await again.connect()
    assert await again.greeting_text() == "Здорова, {name}"
    assert await again.is_enabled() is False
    await again.close()


async def test_статистика(db):
    meme_id = await add(db, 1)
    await db.log_greet(CHAT, USER, meme_id)
    await db.log_greet(CHAT, USER + 1, meme_id)

    stats = await db.stats()
    assert stats["memes"] == 1
    assert stats["greets_total"] == 2
    assert stats["greets_day"] == 2
    assert stats["chats"] == 1
    assert stats["users"] == 2
