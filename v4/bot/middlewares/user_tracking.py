"""
User tracking middleware for analytics
"""

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

logger = logging.getLogger(__name__)


class UserTrackingMiddleware(BaseMiddleware):
    """
    Middleware to track user activity and update statistics.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Get user from event
        user = None
        chat = None

        if isinstance(event, Message):
            user = event.from_user
            chat = event.chat
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            chat = event.message.chat if event.message else None

        if user:
            # Store user info in data for handlers
            data["tracked_user"] = {
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "language_code": user.language_code,
                "is_premium": getattr(user, 'is_premium', False),
            }

            if chat:
                data["tracked_chat"] = {
                    "chat_id": chat.id,
                    "chat_type": chat.type,
                    "title": getattr(chat, 'title', None),
                }

            # Update last seen in Redis - use self.redis or get from data
            redis = self.redis or data.get("redis")
            if redis:
                try:
                    await redis.set_cached(
                        f"user_last_seen:{user.id}",
                        {
                            "timestamp": datetime.utcnow().isoformat(),
                            "username": user.username,
                            "first_name": user.first_name,
                        },
                        ttl=86400 * 30  # 30 days
                    )
                except Exception as e:
                    logger.error(f"Error updating user last seen: {e}")

        return await handler(event, data)
