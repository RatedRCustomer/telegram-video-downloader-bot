"""
Redis client for caching and pub/sub
"""
import json
import hashlib
from typing import Optional, Any


class RedisClient:
    """Async Redis client wrapper"""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or 'redis://localhost:6379/0'
        self._redis = None
        self.pubsub = None

    async def connect(self):
        """Connect to Redis"""
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(
            self.redis_url,
            encoding='utf-8',
            decode_responses=True
        )
        await self._redis.ping()

    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()

    # ===== CACHING =====

    async def get_cached(self, key: str) -> Optional[Any]:
        """Get cached data by key"""
        if not self._redis:
            return None
        data = await self._redis.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
        return None

    async def set_cached(self, key: str, data: Any, ttl: int = 3600):
        """Cache data with TTL"""
        if not self._redis:
            return
        if isinstance(data, (dict, list)):
            data = json.dumps(data)
        await self._redis.set(key, data, ex=ttl)

    async def delete_cached(self, key: str):
        """Delete cached entry"""
        if not self._redis:
            return
        await self._redis.delete(key)

    # ===== RATE LIMITING =====

    async def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """
        Check if rate limited using sliding window.
        Returns True if request is allowed, False if limited.
        """
        if not self._redis:
            return True

        current = await self._redis.incr(key)
        if current == 1:
            await self._redis.expire(key, window_seconds)

        return current <= max_requests

    # ===== DOWNLOAD PROGRESS =====

    async def set_progress(self, download_id: str, progress: float, status: str = None):
        """Update download progress"""
        if not self._redis:
            return
        data = {'progress': str(progress)}
        if status:
            data['status'] = status
        await self._redis.hset(f"progress:{download_id}", mapping=data)
        await self._redis.expire(f"progress:{download_id}", 3600)

    async def get_progress(self, download_id: str) -> Optional[dict]:
        """Get download progress"""
        if not self._redis:
            return None
        data = await self._redis.hgetall(f"progress:{download_id}")
        if data:
            return {
                'progress': float(data.get('progress', 0)),
                'status': data.get('status', 'unknown'),
                'error': data.get('error')
            }
        return None

    # ===== PUB/SUB FOR REAL-TIME UPDATES =====

    async def publish_progress(self, download_id: str, progress: float, status: str):
        """Publish progress update"""
        if not self._redis:
            return
        await self._redis.publish(
            f"download:{download_id}",
            json.dumps({'progress': progress, 'status': status})
        )

    async def subscribe_progress(self, download_id: str):
        """Subscribe to progress updates"""
        if not self._redis:
            return None
        self.pubsub = self._redis.pubsub()
        await self.pubsub.subscribe(f"download:{download_id}")
        return self.pubsub

    # ===== STATS =====

    async def get_stats(self) -> dict:
        """Get cache statistics"""
        if not self._redis:
            return {}

        stats = await self._redis.hgetall('cache:stats') or {}
        keys_count = 0
        async for _ in self._redis.scan_iter(match='cache:*'):
            keys_count += 1

        return {
            'cached_items': keys_count,
            'hits': int(stats.get('hits', 0)),
            'misses': int(stats.get('misses', 0)),
        }
