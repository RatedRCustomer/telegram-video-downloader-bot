import asyncio
import logging
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)


class DownloadQueue:
    def __init__(self, max_concurrent: int = 2):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0
        self._waiting = 0

    @property
    def active_count(self) -> int:
        return self._active

    @property
    def waiting_count(self) -> int:
        return self._waiting

    async def submit(
        self, coro_fn: Callable[..., Coroutine], *args: Any, **kwargs: Any,
    ) -> Any:
        self._waiting += 1
        async with self._semaphore:
            self._waiting -= 1
            self._active += 1
            try:
                return await coro_fn(*args, **kwargs)
            finally:
                self._active -= 1
