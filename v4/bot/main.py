"""
Telegram Video Downloader Bot v4.0
Main application with aiogram and webhook support
"""

import asyncio
import logging
import os
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

# Add shared to path
sys.path.insert(0, '/app/shared')

# Import shared modules (using absolute imports since they're added to path)
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


class BotApp:
    """Main bot application"""

    def __init__(self):
        self.config = Config()
        self.redis_client: RedisClient = None
        self.bot: Bot = None
        self.dp: Dispatcher = None
        self.app: web.Application = None

    async def on_startup(self, app: web.Application):
        """Initialize services on startup"""
        logger.info("Starting bot...")

        # Connect Redis (already initialized in create_app)
        if self.redis_client:
            try:
                await self.redis_client.connect()
                logger.info("Redis connected")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}, continuing without cache")

        # Initialize database
        try:
            await init_db(self.config.database_url)
            logger.info("Database initialized")
        except Exception as e:
            logger.warning(f"Database init failed: {e}, continuing without DB")

        # Set webhook if URL is configured
        if self.config.webhook_url:
            webhook_url = f"{self.config.webhook_url}{self.config.webhook_path}"
            await self.bot.set_webhook(
                url=webhook_url,
                allowed_updates=["message", "callback_query", "inline_query"],
                drop_pending_updates=True
            )
            logger.info(f"Webhook set to {webhook_url}")
        else:
            logger.info("No webhook URL configured, running in polling mode")

    async def on_shutdown(self, app: web.Application):
        """Cleanup on shutdown"""
        logger.info("Shutting down...")

        # Remove webhook
        if self.config.webhook_url:
            await self.bot.delete_webhook()

        # Close Redis
        if self.redis_client:
            await self.redis_client.close()

        # Close bot session
        await self.bot.session.close()

        logger.info("Shutdown complete")

    def create_dispatcher(self) -> Dispatcher:
        """Create and configure dispatcher with routers"""
        dispatcher = Dispatcher()

        # Add middlewares (pass redis_client to all middlewares)
        dispatcher.message.middleware(RateLimitMiddleware(self.redis_client, self.config))
        dispatcher.message.middleware(UserTrackingMiddleware(self.redis_client))
        dispatcher.callback_query.middleware(UserTrackingMiddleware(self.redis_client))

        # Include routers
        dispatcher.include_router(commands.router)
        dispatcher.include_router(messages.router)
        dispatcher.include_router(callbacks.router)
        dispatcher.include_router(inline.router)

        return dispatcher

    def create_app(self) -> web.Application:
        """Create aiohttp web application"""
        # Initialize bot
        self.bot = Bot(
            token=self.config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

        # Pre-initialize Redis client (will be connected in on_startup)
        self.redis_client = RedisClient(self.config.redis_url)

        # Create dispatcher (needs redis_client to be set)
        self.dp = self.create_dispatcher()

        # Store config and redis in dispatcher for handlers to access
        self.dp["config"] = self.config
        self.dp["redis"] = self.redis_client

        # Create web app
        self.app = web.Application()
        self.app.on_startup.append(self.on_startup)
        self.app.on_shutdown.append(self.on_shutdown)

        # Setup webhook handler
        webhook_handler = SimpleRequestHandler(
            dispatcher=self.dp,
            bot=self.bot,
        )
        webhook_handler.register(self.app, path=self.config.webhook_path)

        # Health check endpoint
        async def health_check(request):
            redis_ok = self.redis_client is not None and self.redis_client._redis is not None
            return web.json_response({
                "status": "ok",
                "version": "4.0.0",
                "redis": redis_ok
            })

        self.app.router.add_get("/health", health_check)

        # Metrics endpoint for monitoring
        async def metrics(request):
            if self.redis_client:
                stats = await self.redis_client.get_stats()
            else:
                stats = {}
            return web.json_response(stats)

        self.app.router.add_get("/metrics", metrics)

        return self.app

    async def run_polling(self):
        """Run bot in polling mode"""
        # Initialize bot
        self.bot = Bot(
            token=self.config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

        # Initialize Redis
        self.redis_client = RedisClient(self.config.redis_url)
        try:
            await self.redis_client.connect()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, continuing without cache")

        # Initialize database
        try:
            await init_db(self.config.database_url)
            logger.info("Database initialized")
        except Exception as e:
            logger.warning(f"Database init failed: {e}, continuing without DB")

        # Create dispatcher
        self.dp = self.create_dispatcher()

        # Store config and redis in dispatcher for handlers to access
        self.dp["config"] = self.config
        self.dp["redis"] = self.redis_client

        # Delete any existing webhook
        await self.bot.delete_webhook(drop_pending_updates=True)

        logger.info("Starting bot in polling mode...")

        # Start polling
        try:
            await self.dp.start_polling(
                self.bot,
                allowed_updates=["message", "callback_query", "inline_query"]
            )
        finally:
            await self.bot.session.close()
            if self.redis_client:
                await self.redis_client.close()

    def run_webhook(self):
        """Run bot in webhook mode"""
        app = self.create_app()
        web.run_app(
            app,
            host="0.0.0.0",
            port=self.config.webhook_port,
        )

    def run(self):
        """Run the bot in appropriate mode"""
        if self.config.webhook_url:
            logger.info("Running in webhook mode")
            self.run_webhook()
        else:
            logger.info("Running in polling mode")
            asyncio.run(self.run_polling())


def main():
    """Main entry point"""
    bot_app = BotApp()
    bot_app.run()


if __name__ == "__main__":
    main()
