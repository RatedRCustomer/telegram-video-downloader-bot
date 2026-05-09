from aiogram import Dispatcher

from bot.config import Config
from bot.db import Database
from bot.downloader.engine import DownloadEngine
from bot.services.queue import DownloadQueue


def register_handlers(
    dp: Dispatcher,
    config: Config,
    db: Database,
    engine: DownloadEngine,
    queue: DownloadQueue,
) -> None:
    from bot.handlers.commands import router as cmd_router, setup_command_handlers
    from bot.handlers.callbacks import router as cb_router, setup_callback_handlers
    from bot.handlers.messages import router as msg_router, setup_message_handler

    setup_command_handlers(config, db)
    setup_callback_handlers(config, db, engine, queue)
    setup_message_handler(config, db, engine, queue)

    dp.include_router(cmd_router)
    dp.include_router(cb_router)
    dp.include_router(msg_router)
