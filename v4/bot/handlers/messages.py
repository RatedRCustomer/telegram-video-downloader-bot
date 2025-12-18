"""
Message handlers for URL processing
"""

import logging
import re
from urllib.parse import urlparse

from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from keyboards.quality import get_quality_keyboard
from utils.url_validator import is_valid_video_url, detect_platform

router = Router(name="messages")
logger = logging.getLogger(__name__)

# URL pattern
URL_PATTERN = re.compile(
    r'https?://(?:www\.)?'
    r'(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/|'
    r'instagram\.com/(?:p/|reel/|stories/)|'
    r'tiktok\.com/|vm\.tiktok\.com/|'
    r'twitter\.com/|x\.com/|'
    r'facebook\.com/|fb\.watch/|'
    r'reddit\.com/|v\.redd\.it/|'
    r'threads\.net/|'
    r'twitch\.tv/\w+/clip/)'
    r'[^\s<>"\']+'
)


@router.message(F.text.regexp(URL_PATTERN))
async def handle_video_url(message: Message):
    """Handle messages containing video URLs"""
    # Extract URL from message
    match = URL_PATTERN.search(message.text)
    if not match:
        return

    url = match.group(0)
    logger.info(f"Processing URL: {url} from user {message.from_user.id}")

    # Validate URL
    if not is_valid_video_url(url):
        await message.reply("❌ Невірне або непідтримуване посилання")
        return

    # Detect platform
    platform = detect_platform(url)
    platform_emoji = get_platform_emoji(platform)

    # Send processing message
    processing_msg = await message.reply(
        f"{platform_emoji} <b>Обробка посилання...</b>\n"
        f"Платформа: {platform.title()}\n\n"
        f"⏳ Отримання інформації про відео..."
    )

    # Get video info from cache or API
    redis = message.bot.get("redis")
    config = message.bot.get("config")

    # Try to get from cache
    cache_key = f"video_info:{url}"
    video_info = None

    if redis:
        video_info = await redis.get_cached(cache_key)

    if not video_info:
        # Fetch video info from yt-dlp service
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{config.ytdlp_service_url}/info",
                    json={"url": url},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        video_info = await resp.json()
                        # Cache for 1 hour
                        if redis:
                            await redis.set_cached(cache_key, video_info, ttl=3600)
                    else:
                        error_data = await resp.json()
                        await processing_msg.edit_text(
                            f"❌ <b>Помилка отримання інформації</b>\n\n"
                            f"{error_data.get('error', 'Невідома помилка')}"
                        )
                        return
        except Exception as e:
            logger.error(f"Error fetching video info: {e}")
            await processing_msg.edit_text(
                f"❌ <b>Помилка з'єднання</b>\n\n"
                f"Не вдалося отримати інформацію про відео.\n"
                f"Спробуйте пізніше."
            )
            return

    # Check if video exists
    if not video_info.get("has_video", True):
        await processing_msg.edit_text(
            f"❌ <b>Відео не знайдено</b>\n\n"
            f"Це посилання не містить відео або воно недоступне."
        )
        return

    # Format video info
    title = video_info.get("title", "Без назви")[:100]
    duration = video_info.get("duration", 0)
    duration_str = format_duration(duration)
    thumbnail = video_info.get("thumbnail")

    # Build info message
    info_text = (
        f"{platform_emoji} <b>{title}</b>\n\n"
        f"⏱ Тривалість: {duration_str}\n"
    )

    if video_info.get("view_count"):
        info_text += f"👁 Перегляди: {format_number(video_info['view_count'])}\n"

    if video_info.get("uploader"):
        info_text += f"👤 Автор: {video_info['uploader']}\n"

    info_text += "\n<b>Виберіть якість:</b>"

    # Store URL for callback
    if redis:
        await redis.set_cached(
            f"pending_url:{message.from_user.id}:{processing_msg.message_id}",
            {"url": url, "platform": platform, "info": video_info},
            ttl=300  # 5 minutes
        )

    # Send quality selection
    try:
        if thumbnail:
            # Delete processing message and send new one with thumbnail
            await processing_msg.delete()
            await message.reply_photo(
                photo=thumbnail,
                caption=info_text,
                reply_markup=get_quality_keyboard(
                    url,
                    platform,
                    processing_msg.message_id,
                    show_audio=platform == "youtube"
                )
            )
        else:
            await processing_msg.edit_text(
                info_text,
                reply_markup=get_quality_keyboard(
                    url,
                    platform,
                    processing_msg.message_id,
                    show_audio=platform == "youtube"
                )
            )
    except TelegramBadRequest as e:
        logger.error(f"Error updating message: {e}")


def get_platform_emoji(platform: str) -> str:
    """Get emoji for platform"""
    emojis = {
        "youtube": "🔴",
        "instagram": "📸",
        "tiktok": "🎵",
        "twitter": "🐦",
        "facebook": "📘",
        "reddit": "🤖",
        "threads": "🧵",
        "twitch": "🟣",
    }
    return emojis.get(platform, "🎬")


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable string"""
    if not seconds:
        return "Невідомо"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_number(num: int) -> str:
    """Format large numbers with K/M suffix"""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)
