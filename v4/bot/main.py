"""
Telegram Video Downloader Bot v4.0
Main application with aiogram and webhook support
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from aiohttp import web
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# Add shared to path
sys.path.insert(0, '/app/shared')

from config import Config
from redis_client import RedisClient
from models import init_db

from handlers import commands, messages, callbacks, inline
from middlewares.rate_limit import RateLimitMiddleware
from middlewares.user_tracking import UserTrackingMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
config = Config()
redis_client: RedisClient = None
bot: Bot = None
dp: Dispatcher = None


async def on_startup(app: web.Application):
    """Initialize services on startup"""
    global redis_client, bot

    logger.info("Starting bot...")

    # Initialize Redis
    redis_client = RedisClient(config.redis_url)
    await redis_client.connect()
    logger.info("Redis connected")

    # Initialize database
    await init_db(config.database_url)
    logger.info("Database initialized")

    # Set webhook
    webhook_url = f"{config.webhook_url}{config.webhook_path}"
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query", "inline_query"],
        drop_pending_updates=True
    )
    logger.info(f"Webhook set to {webhook_url}")


async def on_shutdown(app: web.Application):
    """Cleanup on shutdown"""
    global redis_client, bot

    logger.info("Shutting down...")

    # Remove webhook
    await bot.delete_webhook()

    # Close Redis
    if redis_client:
        await redis_client.close()

    # Close bot session
    await bot.session.close()

    logger.info("Shutdown complete")


def create_dispatcher() -> Dispatcher:
    """Create and configure dispatcher with routers"""
    dispatcher = Dispatcher()

    # Add middlewares
    dispatcher.message.middleware(RateLimitMiddleware(redis_client, config))
    dispatcher.message.middleware(UserTrackingMiddleware())
    dispatcher.callback_query.middleware(UserTrackingMiddleware())

    # Include routers
    dispatcher.include_router(commands.router)
    dispatcher.include_router(messages.router)
    dispatcher.include_router(callbacks.router)
    dispatcher.include_router(inline.router)

    return dispatcher


def create_app() -> web.Application:
    """Create aiohttp web application"""
    global bot, dp

    # Initialize bot
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Create dispatcher
    dp = create_dispatcher()

    # Store config and redis in dispatcher for handlers
    dp["config"] = config
    dp["redis"] = redis_client
    dp["bot"] = bot

    # Create web app
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # Setup webhook handler
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_handler.register(app, path=config.webhook_path)

    # Health check endpoint
    async def health_check(request):
        return web.json_response({
            "status": "ok",
            "version": "4.0.0",
            "redis": redis_client is not None and redis_client._redis is not None
        })

    app.router.add_get("/health", health_check)

    # Metrics endpoint for monitoring
    async def metrics(request):
        if redis_client:
            stats = await redis_client.get_stats()
        else:
            stats = {}
        return web.json_response(stats)

    app.router.add_get("/metrics", metrics)

    return app


def main():
    """Main entry point"""
    app = create_app()
    web.run_app(
        app,
        host="0.0.0.0",
        port=config.webhook_port,
    )


if __name__ == "__main__":
    main()
