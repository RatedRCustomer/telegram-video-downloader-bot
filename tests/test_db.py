import pytest
from bot.db import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_init_creates_tables(db):
    tables = await db.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = [row[0] for row in tables]
    assert "downloads" in names
    assert "stats" in names


@pytest.mark.asyncio
async def test_cache_miss_returns_none(db):
    result = await db.get_cached("nonexistent_hash")
    assert result is None


@pytest.mark.asyncio
async def test_cache_store_and_retrieve(db):
    await db.cache_download(
        url_hash="abc123",
        platform="youtube",
        media_type="video",
        file_id="telegram_file_id_here",
        title="Test Video",
        duration=180,
        file_size=10_000_000,
    )
    result = await db.get_cached("abc123")
    assert result is not None
    assert result["file_id"] == "telegram_file_id_here"
    assert result["title"] == "Test Video"
    assert result["platform"] == "youtube"


@pytest.mark.asyncio
async def test_cache_duplicate_url_hash_updates(db):
    await db.cache_download(
        url_hash="dup", platform="youtube", media_type="video",
        file_id="old_id", title="Old", duration=60, file_size=1000,
    )
    await db.cache_download(
        url_hash="dup", platform="youtube", media_type="video",
        file_id="new_id", title="New", duration=60, file_size=1000,
    )
    result = await db.get_cached("dup")
    assert result["file_id"] == "new_id"


@pytest.mark.asyncio
async def test_record_stat_and_get_user_stats(db):
    await db.record_stat(
        user_id=111, username="testuser", chat_id=222,
        platform="youtube", media_type="video", file_size=5_000_000,
    )
    await db.record_stat(
        user_id=111, username="testuser", chat_id=222,
        platform="tiktok", media_type="video", file_size=3_000_000,
    )
    stats = await db.get_user_stats(111)
    assert stats["total_downloads"] == 2
    assert stats["total_bytes"] == 8_000_000
    assert stats["platforms"]["youtube"] == 1
    assert stats["platforms"]["tiktok"] == 1


@pytest.mark.asyncio
async def test_cleanup_old_cache(db):
    await db.execute(
        "INSERT INTO downloads (url_hash, platform, media_type, file_id, title, created_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now', '-60 days'))",
        ("old_hash", "youtube", "video", "fid", "Old Video"),
    )
    await db.execute(
        "INSERT INTO downloads (url_hash, platform, media_type, file_id, title) "
        "VALUES (?, ?, ?, ?, ?)",
        ("new_hash", "youtube", "video", "fid2", "New Video"),
    )
    deleted = await db.cleanup_old_cache(max_age_days=30)
    assert deleted == 1
    assert await db.get_cached("old_hash") is None
    assert await db.get_cached("new_hash") is not None
