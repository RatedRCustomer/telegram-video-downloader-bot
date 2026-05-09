import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_config
from bot.db import Database
from bot.downloader.engine import DownloadEngine
from bot.handlers import register_handlers
from bot.services.cleanup import setup_scheduler
from bot.services.queue import DownloadQueue


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

    engine = DownloadEngine(config)
    queue = DownloadQueue(max_concurrent=config.max_concurrent_downloads)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    register_handlers(dp, config, db, engine, queue)

    scheduler = setup_scheduler(config, db)
    scheduler.start()
    log.info("Cleanup scheduler started (every %dh)", config.cleanup_interval_hours)

    log.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await db.close()
        await bot.session.close()
        log.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
