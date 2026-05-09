import asyncio
import pytest
from bot.services.queue import DownloadQueue


@pytest.mark.asyncio
async def test_queue_respects_concurrency_limit():
    queue = DownloadQueue(max_concurrent=2)
    running = []
    completed = []

    async def task(n):
        running.append(n)
        peak = len(running)
        await asyncio.sleep(0.05)
        running.remove(n)
        completed.append(n)
        return peak

    results = await asyncio.gather(
        queue.submit(task, 1),
        queue.submit(task, 2),
        queue.submit(task, 3),
    )
    assert all(r <= 2 for r in results)
    assert len(completed) == 3


@pytest.mark.asyncio
async def test_queue_propagates_errors():
    queue = DownloadQueue(max_concurrent=2)

    async def failing():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        await queue.submit(failing)
