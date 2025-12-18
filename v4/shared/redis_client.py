"""
Redis client for caching and pub/sub
"""
import json
import hashlib
from typing import Optional, Any
from datetime import timedelta

import redis.asyncio as redis

from .config import config


class RedisClient:
    """Async Redis client wrapper"""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None

    async def connect(self):
        """Connect to Redis"""
        self.redis = redis.from_url(
            config.redis_url,
            encoding='utf-8',
            decode_responses=True
        )
        await self.redis.ping()

    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()

    # ===== CACHING =====

    @staticmethod
    def get_cache_key(url: str, quality: str, format: str) -> str:
        """Generate cache key for URL+quality+format"""
        key = f"{url}_{quality}_{format}"
        return f"cache:{hashlib.md5(key.encode()).hexdigest()}"

    async def get_cached(self, url: str, quality: str, format: str) -> Optional[dict]:
        """Get cached video info"""
        key = self.get_cache_key(url, quality, format)
        data = await self.redis.get(key)
        if data:
            # Update access stats
            await self.redis.hincrby('cache:stats', 'hits', 1)
            return json.loads(data)
        await self.redis.hincrby('cache:stats', 'misses', 1)
        return None

    async def set_cached(self, url: str, quality: str, format: str, data: dict, ttl: int = None):
        """Cache video info"""
        key = self.get_cache_key(url, quality, format)
        ttl = ttl or config.cache_ttl
        await self.redis.set(key, json.dumps(data), ex=ttl)

    async def delete_cached(self, url: str, quality: str, format: str):
        """Delete cached entry"""
        key = self.get_cache_key(url, quality, format)
        await self.redis.delete(key)

    # ===== VIDEO INFO CACHE =====

    async def get_video_info(self, url: str) -> Optional[dict]:
        """Get cached video info (metadata only)"""
        key = f"info:{hashlib.md5(url.encode()).hexdigest()}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def set_video_info(self, url: str, info: dict):
        """Cache video info"""
        key = f"info:{hashlib.md5(url.encode()).hexdigest()}"
        await self.redis.set(key, json.dumps(info), ex=config.info_cache_ttl)

    # ===== RATE LIMITING =====

    async def check_rate_limit(self, user_id: int, is_group: bool = False) -> tuple[bool, int]:
        """
        Check if user/group is rate limited
        Returns: (is_limited, seconds_remaining)
        """
        key = f"rate:{'group' if is_group else 'user'}:{user_id}"
        limit = config.rate_limit_group if is_group else config.rate_limit_user

        ttl = await self.redis.ttl(key)
        if ttl > 0:
            return True, ttl

        # Set rate limit
        await self.redis.set(key, '1', ex=limit)
        return False, 0

    async def reset_rate_limit(self, user_id: int, is_group: bool = False):
        """Reset rate limit for user/group"""
        key = f"rate:{'group' if is_group else 'user'}:{user_id}"
        await self.redis.delete(key)

    # ===== DOWNLOAD PROGRESS =====

    async def set_progress(self, download_id: str, progress: float, status: str = None):
        """Update download progress"""
        data = {'progress': progress}
        if status:
            data['status'] = status
        await self.redis.hset(f"progress:{download_id}", mapping=data)
        await self.redis.expire(f"progress:{download_id}", 3600)

    async def get_progress(self, download_id: str) -> Optional[dict]:
        """Get download progress"""
        data = await self.redis.hgetall(f"progress:{download_id}")
        if data:
            return {
                'progress': float(data.get('progress', 0)),
                'status': data.get('status', 'unknown')
            }
        return None

    # ===== PUB/SUB FOR REAL-TIME UPDATES =====

    async def publish_progress(self, download_id: str, progress: float, status: str):
        """Publish progress update"""
        await self.redis.publish(
            f"download:{download_id}",
            json.dumps({'progress': progress, 'status': status})
        )

    async def subscribe_progress(self, download_id: str):
        """Subscribe to progress updates"""
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(f"download:{download_id}")
        return self.pubsub

    # ===== STATS =====

    async def get_stats(self) -> dict:
        """Get cache statistics"""
        stats = await self.redis.hgetall('cache:stats') or {}
        keys_count = 0
        async for _ in self.redis.scan_iter(match='cache:*'):
            keys_count += 1

        return {
            'cached_items': keys_count,
            'hits': int(stats.get('hits', 0)),
            'misses': int(stats.get('misses', 0)),
        }


# Global instance
redis_client = RedisClient()
