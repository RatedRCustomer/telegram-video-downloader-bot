"""
Message handlers for URL processing
Supports videos, photos, carousels with captions
"""

import logging
import re
from urllib.parse import urlparse

from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from keyboards.quality import get_quality_keyboard, get_media_keyboard
from utils.url_validator import is_valid_url, detect_platform

router = Router(name="messages")
logger = logging.getLogger(__name__)

# URL pattern - extended to support more platforms and post types
URL_PATTERN = re.compile(
    r'https?://(?:www\.)?'
    r'(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/|'
    r'instagram\.com/(?:p/|reel/|reels/|stories/|tv/)|'
    r'tiktok\.com/|vm\.tiktok\.com/|'
    r'twitter\.com/|x\.com/|'
    r'facebook\.com/|fb\.watch/|'
    r'reddit\.com/|v\.redd\.it/|'
    r'threads\.net/|'
    r'twitch\.tv/\w+/clip/|clips\.twitch\.tv/|'
    r'pinterest\.com/pin/|pin\.it/)'
    r'[^\s<>"\']+'
)


@router.message(F.text.regexp(URL_PATTERN))
async def handle_media_url(message: Message):
    """Handle messages containing media URLs (videos, photos, carousels)"""
    # Extract URL from message
    match = URL_PATTERN.search(message.text)
    if not match:
        return

    url = match.group(0)
    logger.info(f"Processing URL: {url} from user {message.from_user.id}")

    # Validate URL
    if not is_valid_url(url):
        await message.reply("❌ Невірне або непідтримуване посилання")
        return

    # Detect platform
    platform = detect_platform(url)
    platform_emoji = get_platform_emoji(platform)

    # Send processing message
    processing_msg = await message.reply(
        f"{platform_emoji} <b>Обробка посилання...</b>\n"
        f"Платформа: {platform.title()}\n\n"
        f"⏳ Отримання інформації..."
    )

    # Get media info from Celery task
    redis = message.bot.get("redis")
    config = message.bot.get("config")

    # Try to get from cache
    cache_key = f"media_info:{url}"
    media_info = None

    if redis:
        media_info = await redis.get_cached(cache_key)

    if not media_info:
        # Send task to get media info
        from celery import Celery
        celery_app = Celery(
            'tasks',
            broker=config.celery_broker_url if config else 'redis://redis:6379/0',
            backend=config.celery_result_backend if config else 'redis://redis:6379/0'
        )

        try:
            # Call the get_media_info task synchronously (with timeout)
            result = celery_app.send_task(
                'tasks.get_media_info',
                args=[url, platform],
                queue='downloads'
            )
            media_info = result.get(timeout=30)

            if media_info and not media_info.get('error'):
                # Cache for 1 hour
                if redis:
                    await redis.set_cached(cache_key, media_info, ttl=3600)
        except Exception as e:
            logger.error(f"Error fetching media info: {e}")
            await processing_msg.edit_text(
                f"❌ <b>Помилка отримання інформації</b>\n\n"
                f"Спробуйте пізніше."
            )
            return

    if media_info and media_info.get('error'):
        await processing_msg.edit_text(
            f"❌ <b>Помилка</b>\n\n"
            f"{media_info.get('error', 'Невідома помилка')}"
        )
        return

    # Determine content type
    has_video = media_info.get('has_video', False)
    has_photo = media_info.get('has_photo', False)
    is_carousel = media_info.get('is_carousel', False)
    media_count = media_info.get('media_count', 1)

    # Format info message
    title = media_info.get('title', '')[:100]
    description = media_info.get('description', '')[:300]
    uploader = media_info.get('uploader', '')
    thumbnail = media_info.get('thumbnail')

    # Build info message
    if has_video:
        media_type = "🎬 Відео"
        duration = media_info.get('media', [{}])[0].get('duration', 0) if media_info.get('media') else 0
        duration_str = format_duration(duration)
    elif has_photo:
        if is_carousel:
            media_type = f"🖼 Карусель ({media_count} фото)"
        else:
            media_type = "🖼 Фото"
        duration_str = None
    else:
        media_type = "📎 Медіа"
        duration_str = None

    info_text = f"{platform_emoji} <b>{title or 'Пост'}</b>\n\n"
    info_text += f"📌 Тип: {media_type}\n"

    if duration_str:
        info_text += f"⏱ Тривалість: {duration_str}\n"

    if uploader:
        info_text += f"👤 Автор: {uploader}\n"

    # Add description preview
    if description:
        # Truncate description for preview
        desc_preview = description[:150]
        if len(description) > 150:
            desc_preview += "..."
        info_text += f"\n<i>{desc_preview}</i>\n"

    info_text += "\n<b>Виберіть дію:</b>"

    # Store URL data for callback
    if redis:
        await redis.set_cached(
            f"pending_url:{message.from_user.id}:{processing_msg.message_id}",
            {
                "url": url,
                "platform": platform,
                "info": media_info,
                "has_video": has_video,
                "has_photo": has_photo,
                "is_carousel": is_carousel,
            },
            ttl=300  # 5 minutes
        )

    # Select keyboard based on content type
    if has_video:
        keyboard = get_quality_keyboard(
            url,
            platform,
            processing_msg.message_id,
            show_audio=platform == "youtube"
        )
    else:
        keyboard = get_media_keyboard(
            url,
            platform,
            processing_msg.message_id,
            is_carousel=is_carousel
        )

    # Send info with thumbnail if available
    try:
        if thumbnail:
            await processing_msg.delete()
            await message.reply_photo(
                photo=thumbnail,
                caption=info_text,
                reply_markup=keyboard
            )
        else:
            await processing_msg.edit_text(
                info_text,
                reply_markup=keyboard
            )
    except TelegramBadRequest as e:
        logger.error(f"Error updating message: {e}")
        # Fallback to text only
        try:
            await processing_msg.edit_text(
                info_text,
                reply_markup=keyboard
            )
        except:
            pass


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
        "pinterest": "📌",
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
