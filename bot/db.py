import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash    TEXT UNIQUE NOT NULL,
    platform    TEXT NOT NULL,
    media_type  TEXT NOT NULL,
    file_id     TEXT NOT NULL,
    title       TEXT,
    duration    INTEGER,
    file_size   INTEGER,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    username    TEXT,
    chat_id     INTEGER NOT NULL,
    platform    TEXT NOT NULL,
    media_type  TEXT NOT NULL,
    file_size   INTEGER,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, db_path: str):
        self._path = db_path
        self._conn: aiosqlite.Connection | None = None

    def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._conn

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        conn = self._ensure_conn()
        await conn.execute(sql, params)
        await conn.commit()

    async def execute_fetchall(self, sql: str, params: tuple = ()) -> list:
        conn = self._ensure_conn()
        cursor = await conn.execute(sql, params)
        return await cursor.fetchall()

    async def get_cached(self, url_hash: str) -> dict | None:
        conn = self._ensure_conn()
        cursor = await conn.execute(
            "SELECT file_id, platform, media_type, title, duration, file_size "
            "FROM downloads WHERE url_hash = ?",
            (url_hash,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def cache_download(
        self,
        url_hash: str,
        platform: str,
        media_type: str,
        file_id: str,
        title: str | None,
        duration: int | None,
        file_size: int | None,
    ) -> None:
        conn = self._ensure_conn()
        await conn.execute(
            "INSERT INTO downloads (url_hash, platform, media_type, file_id, title, duration, file_size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(url_hash) DO UPDATE SET "
            "file_id=excluded.file_id, title=excluded.title, "
            "duration=excluded.duration, file_size=excluded.file_size, "
            "created_at=CURRENT_TIMESTAMP",
            (url_hash, platform, media_type, file_id, title, duration, file_size),
        )
        await conn.commit()

    async def record_stat(
        self,
        user_id: int,
        username: str | None,
        chat_id: int,
        platform: str,
        media_type: str,
        file_size: int | None,
    ) -> None:
        conn = self._ensure_conn()
        await conn.execute(
            "INSERT INTO stats (user_id, username, chat_id, platform, media_type, file_size) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, chat_id, platform, media_type, file_size),
        )
        await conn.commit()

    async def get_user_stats(self, user_id: int) -> dict:
        conn = self._ensure_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) as total, COALESCE(SUM(file_size), 0) as bytes "
            "FROM stats WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        total = row["total"]
        total_bytes = row["bytes"]

        cursor = await conn.execute(
            "SELECT platform, COUNT(*) as cnt FROM stats "
            "WHERE user_id = ? GROUP BY platform",
            (user_id,),
        )
        platforms = {r["platform"]: r["cnt"] for r in await cursor.fetchall()}

        return {
            "total_downloads": total,
            "total_bytes": total_bytes,
            "platforms": platforms,
        }

    async def get_global_stats(self) -> dict:
        conn = self._ensure_conn()

        cursor = await conn.execute(
            "SELECT COUNT(*) as total, COALESCE(SUM(file_size), 0) as bytes FROM stats"
        )
        row = await cursor.fetchone()

        cursor = await conn.execute(
            "SELECT platform, COUNT(*) as cnt FROM stats "
            "GROUP BY platform ORDER BY cnt DESC"
        )
        platforms = {r["platform"]: r["cnt"] for r in await cursor.fetchall()}

        cursor = await conn.execute(
            "SELECT user_id, username, COUNT(*) as cnt FROM stats "
            "GROUP BY user_id ORDER BY cnt DESC LIMIT 10"
        )
        top_users = [(r["user_id"], r["username"], r["cnt"]) for r in await cursor.fetchall()]

        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM downloads")
        cache_count = (await cursor.fetchone())["cnt"]

        return {
            "total_downloads": row["total"],
            "total_bytes": row["bytes"],
            "platforms": platforms,
            "top_users": top_users,
            "cache_entries": cache_count,
        }

    async def cleanup_old_cache(self, max_age_days: int) -> int:
        conn = self._ensure_conn()
        cursor = await conn.execute(
            "DELETE FROM downloads WHERE created_at < datetime('now', ? || ' days')",
            (f"-{max_age_days}",),
        )
        await conn.commit()
        return cursor.rowcount
