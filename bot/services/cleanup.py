import logging
import os
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import Config
from bot.db import Database

log = logging.getLogger(__name__)


async def cleanup_stale_files(download_dir: str, max_age_seconds: int = 3600) -> int:
    now = time.time()
    deleted = 0
    if not os.path.exists(download_dir):
        return 0
    for name in os.listdir(download_dir):
        path = os.path.join(download_dir, name)
        if os.path.isfile(path) and (now - os.path.getmtime(path)) > max_age_seconds:
            try:
                os.unlink(path)
                deleted += 1
                log.info("Cleaned up stale file: %s", name)
            except OSError as e:
                log.warning("Failed to delete %s: %s", name, e)
    return deleted


async def cleanup_old_cache(db: Database, max_age_days: int) -> int:
    deleted = await db.cleanup_old_cache(max_age_days)
    if deleted:
        log.info("Cleaned up %d old cache entries", deleted)
    return deleted


def setup_scheduler(config: Config, db: Database) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        cleanup_stale_files,
        "interval",
        hours=config.cleanup_interval_hours,
        args=[config.download_dir],
        id="cleanup_files",
    )

    scheduler.add_job(
        cleanup_old_cache,
        "interval",
        hours=24,
        args=[db, config.cache_ttl_days],
        id="cleanup_cache",
    )

    return scheduler
