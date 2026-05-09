import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from bot.config import load_config
from bot.db import Database
from bot.downloader.engine import DownloadEngine
from bot.handlers import register_handlers
from bot.services.cleanup import setup_scheduler
from bot.services.queue import DownloadQueue


HEARTBEAT_INTERVAL_SEC = 60


async def _heartbeat_loop(path: Path, interval: int = HEARTBEAT_INTERVAL_SEC) -> None:
    """Touch a file periodically so the container healthcheck can verify liveness.

    A stalled event loop (deadlock, process hung) stops touching the file → mtime ages →
    docker healthcheck declares unhealthy. More reliable than `pgrep`, which only proves
    the process exists, not that asyncio is making progress.
    """
    log = logging.getLogger(__name__)
    while True:
        try:
            path.touch(exist_ok=True)
        except Exception as e:
            log.warning("Heartbeat write failed: %s", e)
        await asyncio.sleep(interval)


async def main() -> None:
    config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger(__name__)

    os.makedirs(config.download_dir, exist_ok=True)

    db = Database(config.db_path)
    await db.init()
    log.info("Database initialized at %s", config.db_path)

    # Warn early if yt-dlp cookies file is stale; admin can refresh via /cookies.
    if config.cookies_file:
        cookies_path = Path(config.cookies_file)
        if cookies_path.exists():
            age_days = (time.time() - cookies_path.stat().st_mtime) / 86400
            if age_days > 7:
                log.warning(
                    "Cookies file is %.1f days old (%s) — admin should /cookies refresh",
                    age_days, cookies_path,
                )
            else:
                log.info("Cookies file age: %.1f days", age_days)
        else:
            log.info(
                "Cookies file not present (%s) — yt-dlp will run anonymously",
                cookies_path,
            )

    engine = DownloadEngine(config)
    queue = DownloadQueue(max_concurrent=config.max_concurrent_downloads)

    if config.tg_api_url:
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(config.tg_api_url, is_local=False)
        )
        bot = Bot(
            token=config.bot_token,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        log.info("Using local Telegram Bot API at %s", config.tg_api_url)
    else:
        bot = Bot(
            token=config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        log.info("Using Telegram cloud Bot API")
    dp = Dispatcher()

    register_handlers(dp, config, db, engine, queue)

    scheduler = setup_scheduler(config, db)
    scheduler.start()
    log.info("Cleanup scheduler started (every %dh)", config.cleanup_interval_hours)

    heartbeat_path = Path(config.download_dir).parent / ".heartbeat"
    heartbeat_path.touch(exist_ok=True)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(heartbeat_path))
    log.info("Heartbeat at %s every %ds", heartbeat_path, HEARTBEAT_INTERVAL_SEC)

    log.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot)
    finally:
        heartbeat_task.cancel()
        scheduler.shutdown()
        await db.close()
        await bot.session.close()
        log.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
