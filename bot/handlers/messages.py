import asyncio
import logging
import os
import time

import aiohttp
from aiogram import Bot, F, Router, types
from aiogram.types import FSInputFile

from bot.config import Config
from bot.db import Database
from bot.downloader.engine import DownloadEngine, DownloadResult
from bot.downloader.platforms import (
    DownloadTool,
    MediaType,
    Platform,
    PlatformMatch,
    extract_urls,
    identify_platform,
    is_short_url,
    resolve_short_url,
)
from bot.downloader.progress import (
    ProgressThrottle,
    format_progress_bar,
    parse_ytdlp_progress,
)
from bot.services.queue import DownloadQueue

log = logging.getLogger(__name__)

router = Router()

_rate_limits: dict[int, list[float]] = {}
_last_rate_cleanup = 0.0

# Cache bot username to avoid calling bot.get_me() on every message
_bot_username: str | None = None


async def _get_bot_username(bot: Bot) -> str | None:
    global _bot_username
    if _bot_username is None:
        try:
            me = await bot.get_me()
            _bot_username = me.username
        except Exception:
            return None
    return _bot_username


def _check_rate_limit(user_id: int, max_per_minute: int) -> bool:
    global _last_rate_cleanup
    now = time.time()

    # Periodic cleanup of stale entries (every 5 minutes)
    if now - _last_rate_cleanup > 300:
        _last_rate_cleanup = now
        expired = [
            uid for uid, ts in _rate_limits.items()
            if not ts or now - max(ts) > 60
        ]
        for uid in expired:
            del _rate_limits[uid]

    timestamps = _rate_limits.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < 60]
    _rate_limits[user_id] = timestamps
    if len(timestamps) >= max_per_minute:
        return True
    timestamps.append(now)
    return False


async def _send_result(
    message: types.Message,
    result: DownloadResult,
    cached: bool = False,
) -> str:
    caption_parts = [result.title]
    if result.media_type == MediaType.VIDEO:
        caption_parts.append(f"{result.file_size / 1_000_000:.1f} MB")
    if result.duration:
        mins, secs = divmod(result.duration, 60)
        caption_parts.append(f"{mins}:{secs:02d}")
    if cached:
        caption_parts.append("\u26a1 з кешу")
    caption = " | ".join(caption_parts)

    if result.media_type == MediaType.AUDIO:
        sent = await message.reply_audio(
            FSInputFile(result.file_path),
            caption=caption,
            title=result.title,
        )
        return sent.audio.file_id
    else:
        sent = await message.reply_video(
            FSInputFile(result.file_path),
            caption=caption,
            supports_streaming=True,
        )
        return sent.video.file_id


async def _process_url(
    message: types.Message,
    match: PlatformMatch,
    bot: Bot,
    config: Config,
    db: Database,
    engine: DownloadEngine,
    queue: DownloadQueue,
):
    user_id = message.from_user.id if message.from_user else 0
    username = message.from_user.username if message.from_user else None
    chat_id = message.chat.id
    url_hash = engine.url_hash(match.url, "auto")

    cached = await db.get_cached(url_hash)
    if cached:
        try:
            if cached["media_type"] == "audio":
                await message.reply_audio(
                    cached["file_id"],
                    caption=f"{cached.get('title', 'Audio')} | \u26a1 з кешу",
                )
            else:
                await message.reply_video(
                    cached["file_id"],
                    caption=f"{cached.get('title', 'Video')} | \u26a1 з кешу",
                )
            await db.record_stat(
                user_id, username, chat_id,
                match.platform.value, match.media_type.value,
                cached.get("file_size"),
            )
            return
        except Exception as e:
            log.warning("Cache send failed, re-downloading: %s", e)

    if queue.active_count >= config.max_concurrent_downloads:
        pos = queue.waiting_count + 1
        status_msg = await message.reply(f"\u23f3 В черзі, позиція: {pos}")
    else:
        status_msg = await message.reply(
            f"\u2b07\ufe0f Завантажую з {match.platform.value}..."
        )

    throttle = ProgressThrottle(interval=3.0)

    async def on_progress(line: str):
        parsed = parse_ytdlp_progress(line)
        if parsed and throttle.should_update():
            bar = format_progress_bar(parsed["percent"], parsed["speed"])
            try:
                await status_msg.edit_text(bar)
            except Exception:
                pass

    try:
        result = await queue.submit(engine.download, match, "auto", on_progress)
    except ValueError as e:
        await status_msg.edit_text(f"\u26a0\ufe0f {e}")
        return
    except Exception:
        log.exception("Download failed for %s", match.url)
        await status_msg.edit_text(
            "\u274c Не вдалось завантажити. Можливо, відео приватне або видалене."
        )
        return

    try:
        file_id = await _send_result(message, result)
        await db.cache_download(
            url_hash=url_hash,
            platform=match.platform.value,
            media_type=result.media_type.value,
            file_id=file_id,
            title=result.title,
            duration=result.duration,
            file_size=result.file_size,
        )
        await db.record_stat(
            user_id, username, chat_id,
            match.platform.value, result.media_type.value, result.file_size,
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception:
        log.exception("Failed to send file to Telegram")
        await status_msg.edit_text(
            "\u274c Не вдалось відправити файл в Telegram."
        )
    finally:
        try:
            if os.path.exists(result.file_path):
                os.unlink(result.file_path)
        except Exception:
            pass


def setup_message_handler(
    config: Config,
    db: Database,
    engine: DownloadEngine,
    queue: DownloadQueue,
):
    @router.message(F.text)
    async def handle_message(message: types.Message, bot: Bot):
        if not message.text or not message.from_user:
            return

        # Sanitize text: replace surrogate characters that crash urllib
        try:
            text = message.text.encode("utf-8", errors="replace").decode("utf-8")
        except Exception:
            return

        user_id = message.from_user.id

        if _check_rate_limit(user_id, config.rate_limit_per_minute):
            await message.reply("\U0001f422 Забагато запитів, зачекай трохи.")
            return

        urls = extract_urls(text)
        if not urls:
            return

        bot_name = await _get_bot_username(bot)
        bot_mentioned = f"@{bot_name}" in text if bot_name else False

        for url in urls[:3]:
            if is_short_url(url):
                resolved = await resolve_short_url(url)
                if resolved:
                    url = resolved
                else:
                    continue

            match = identify_platform(url)

            if match is None:
                if bot_mentioned:
                    match = PlatformMatch(
                        platform=Platform.YOUTUBE,
                        media_type=MediaType.VIDEO,
                        tool=DownloadTool.YTDLP,
                        url=url,
                    )
                else:
                    continue

            asyncio.create_task(
                _process_url(message, match, bot, config, db, engine, queue)
            )

    return router
