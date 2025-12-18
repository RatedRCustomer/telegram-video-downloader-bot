"""
Rate limiting middleware using Redis
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """
    Rate limiting middleware using Redis.
    Limits requests per user to prevent abuse.
    """

    def __init__(self, redis_client, config):
        self.redis = redis_client
        self.config = config
        self.rate_limit = getattr(config, 'rate_limit_per_minute', 10)
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # Skip rate limiting for admins
        if self.config and event.from_user.id in getattr(self.config, 'admin_ids', []):
            return await handler(event, data)

        # Check rate limit
        if self.redis:
            user_id = event.from_user.id
            is_allowed = await self.redis.check_rate_limit(
                f"rate:{user_id}",
                self.rate_limit,
                60  # 1 minute window
            )

            if not is_allowed:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                await event.answer(
                    "⚠️ <b>Занадто багато запитів</b>\n\n"
                    f"Ви можете надсилати до {self.rate_limit} запитів на хвилину.\n"
                    "Зачекайте трохи і спробуйте знову.",
                    parse_mode="HTML"
                )
                return

        return await handler(event, data)
