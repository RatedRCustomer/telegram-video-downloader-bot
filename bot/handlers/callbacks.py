import logging
import os
import time

import aiohttp
from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import Config
from bot.db import Database
from bot.downloader.engine import DownloadEngine
from bot.downloader.platforms import (
    MediaType,
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

# Store pending quality selections with TTL
_pending: dict[str, tuple[PlatformMatch, float]] = {}
_PENDING_TTL = 300  # 5 minutes


def _cleanup_pending() -> None:
    now = time.time()
    expired = [k for k, (_, ts) in _pending.items() if now - ts > _PENDING_TTL]
    for k in expired:
        del _pending[k]


def setup_callback_handlers(
    config: Config,
    db: Database,
    engine: DownloadEngine,
    queue: DownloadQueue,
):
    @router.message(Command("quality"))
    async def cmd_quality(message: Message, bot: Bot):
        if not message.text or not message.from_user:
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Використання: /quality <посилання>")
            return

        url = parts[1].strip()
        urls = extract_urls(url)
        if not urls:
            await message.reply("\u274c Не знайдено посилання.")
            return

        target_url = urls[0]

        if is_short_url(target_url):
            resolved = await resolve_short_url(target_url)
            if resolved:
                target_url = resolved
            else:
                await message.reply("\u274c Не вдалось розпізнати посилання.")
                return

        match = identify_platform(target_url)
        if match is None:
            await message.reply(
                "\u274c Платформа не підтримується для вибору якості."
            )
            return

        _cleanup_pending()
        key = f"{message.from_user.id}:{message.message_id}"
        _pending[key] = (match, time.time())

        title = await engine._get_title(target_url)
        await message.reply(
            f"\U0001f3ac {title}\n\nОбери якість:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="1080p", callback_data=f"q:{key}:1080"),
                    InlineKeyboardButton(text="720p", callback_data=f"q:{key}:720"),
                    InlineKeyboardButton(text="480p", callback_data=f"q:{key}:480"),
                ],
                [
                    InlineKeyboardButton(
                        text="\U0001f3b5 Audio",
                        callback_data=f"q:{key}:audio",
                    ),
                ],
            ]),
        )

    @router.callback_query(F.data.startswith("q:"))
    async def handle_quality_callback(callback: CallbackQuery, bot: Bot):
        if not callback.data or not callback.message or not callback.from_user:
            return

        parts = callback.data.split(":")
        if len(parts) != 4:
            await callback.answer("\u274c Невірний вибір")
            return

        _, user_id, msg_id, quality = parts
        key = f"{user_id}:{msg_id}"

        _cleanup_pending()
        match_data = _pending.pop(key, None)
        if match_data is None:
            await callback.answer("Сесія закінчилась, спробуй знову.")
            return
        match, _ = match_data

        await callback.answer(f"Завантажую в {quality}...")

        if quality == "audio":
            match = PlatformMatch(
                platform=match.platform,
                media_type=MediaType.AUDIO,
                tool=match.tool,
                url=match.url,
            )
            dl_quality = "auto"
        else:
            dl_quality = quality

        await callback.message.edit_text(f"\u2b07\ufe0f Завантажую в {quality}...")

        throttle = ProgressThrottle(interval=3.0)

        async def on_progress(line: str):
            parsed = parse_ytdlp_progress(line)
            if parsed and throttle.should_update():
                bar = format_progress_bar(parsed["percent"], parsed["speed"])
                try:
                    await callback.message.edit_text(bar)
                except Exception:
                    pass

        try:
            result = await queue.submit(engine.download, match, dl_quality, on_progress)
        except Exception:
            log.exception("Quality download failed")
            await callback.message.edit_text("\u274c Не вдалось завантажити.")
            return

        try:
            caption = (
                f"{result.title} | {quality} | "
                f"{result.file_size / 1_000_000:.1f} MB"
            )
            if result.media_type == MediaType.AUDIO:
                sent = await callback.message.reply_audio(
                    FSInputFile(result.file_path),
                    caption=caption,
                    title=result.title,
                )
                file_id = sent.audio.file_id
            else:
                sent = await callback.message.reply_video(
                    FSInputFile(result.file_path),
                    caption=caption,
                    supports_streaming=True,
                )
                file_id = sent.video.file_id

            url_hash = engine.url_hash(match.url, dl_quality)
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
                callback.from_user.id,
                callback.from_user.username,
                callback.message.chat.id,
                match.platform.value,
                result.media_type.value,
                result.file_size,
            )

            try:
                await callback.message.delete()
            except Exception:
                pass

        except Exception:
            log.exception("Failed to send file")
            await callback.message.edit_text("\u274c Не вдалось відправити файл.")
        finally:
            try:
                if os.path.exists(result.file_path):
                    os.unlink(result.file_path)
            except Exception:
                pass

    return router
