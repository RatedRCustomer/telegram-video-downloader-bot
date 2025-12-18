"""
Inline query handlers for @bot URL functionality
"""

import logging
import hashlib
from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultVideo,
    InputTextMessageContent,
)

from utils.url_validator import is_valid_video_url, detect_platform

router = Router(name="inline")
logger = logging.getLogger(__name__)


@router.inline_query()
async def handle_inline_query(inline_query: InlineQuery):
    """Handle inline queries with video URLs"""
    query_text = inline_query.query.strip()

    # If empty query, show help
    if not query_text:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="help",
                    title="📹 Вставте посилання на відео",
                    description="YouTube, Instagram, TikTok, Twitter та інші",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            "💡 <b>Як використовувати inline режим:</b>\n\n"
                            "Введіть: <code>@botname URL</code>\n\n"
                            "Підтримувані платформи:\n"
                            "• YouTube, Instagram, TikTok\n"
                            "• Twitter/X, Facebook, Reddit\n"
                            "• Threads, Twitch Clips"
                        ),
                        parse_mode="HTML"
                    )
                )
            ],
            cache_time=300,
            is_personal=True
        )
        return

    # Check if it's a valid URL
    if not is_valid_video_url(query_text):
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="invalid",
                    title="❌ Невірне посилання",
                    description="Введіть правильне посилання на відео",
                    input_message_content=InputTextMessageContent(
                        message_text="❌ Невірне або непідтримуване посилання"
                    )
                )
            ],
            cache_time=10,
            is_personal=True
        )
        return

    # Detect platform
    platform = detect_platform(query_text)
    platform_emoji = get_platform_emoji(platform)

    # Try to get video info from cache
    redis = inline_query.bot.get("redis")
    config = inline_query.bot.get("config")

    video_info = None
    cache_key = f"video_info:{query_text}"

    if redis:
        video_info = await redis.get_cached(cache_key)

    # If not in cache, try to fetch
    if not video_info:
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{config.ytdlp_service_url}/info",
                    json={"url": query_text},
                    timeout=aiohttp.ClientTimeout(total=10)  # Short timeout for inline
                ) as resp:
                    if resp.status == 200:
                        video_info = await resp.json()
                        if redis:
                            await redis.set_cached(cache_key, video_info, ttl=3600)
        except Exception as e:
            logger.error(f"Error fetching video info for inline: {e}")

    # Build results
    results = []

    if video_info and video_info.get("has_video", True):
        title = video_info.get("title", "Відео")[:64]
        duration = video_info.get("duration", 0)
        thumbnail = video_info.get("thumbnail")
        description = f"{platform.title()} • {format_duration(duration)}"

        if video_info.get("uploader"):
            description += f" • {video_info['uploader']}"

        # Generate unique ID based on URL
        result_id = hashlib.md5(query_text.encode()).hexdigest()[:16]

        # Main video result - sends download command
        results.append(
            InlineQueryResultArticle(
                id=f"video_{result_id}",
                title=f"{platform_emoji} {title}",
                description=description,
                thumbnail_url=thumbnail,
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"{platform_emoji} <b>Завантажити відео</b>\n\n"
                        f"📹 {title}\n"
                        f"🔗 {query_text}\n\n"
                        f"<i>Надішліть це повідомлення боту для завантаження</i>"
                    ),
                    parse_mode="HTML"
                )
            )
        )

        # Quality options
        for quality in ["1080p", "720p", "480p"]:
            results.append(
                InlineQueryResultArticle(
                    id=f"{quality}_{result_id}",
                    title=f"📊 {quality}",
                    description=f"Завантажити в {quality}",
                    thumbnail_url=thumbnail,
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"{platform_emoji} <b>Завантажити в {quality}</b>\n\n"
                            f"📹 {title}\n"
                            f"🔗 {query_text}\n\n"
                            f"<i>Надішліть це повідомлення боту</i>"
                        ),
                        parse_mode="HTML"
                    )
                )
            )

        # Audio option for YouTube
        if platform == "youtube":
            results.append(
                InlineQueryResultArticle(
                    id=f"audio_{result_id}",
                    title="🎵 Тільки аудіо (MP3)",
                    description="Завантажити тільки звук",
                    thumbnail_url=thumbnail,
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"🎵 <b>Завантажити аудіо</b>\n\n"
                            f"🎧 {title}\n"
                            f"🔗 {query_text}\n\n"
                            f"<i>Надішліть це повідомлення боту</i>"
                        ),
                        parse_mode="HTML"
                    )
                )
            )
    else:
        # Video info not available - show basic download option
        result_id = hashlib.md5(query_text.encode()).hexdigest()[:16]

        results.append(
            InlineQueryResultArticle(
                id=f"download_{result_id}",
                title=f"{platform_emoji} Завантажити з {platform.title()}",
                description=query_text[:50],
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"{platform_emoji} <b>Завантажити відео</b>\n\n"
                        f"🔗 {query_text}\n\n"
                        f"<i>Надішліть це повідомлення боту для завантаження</i>"
                    ),
                    parse_mode="HTML"
                )
            )
        )

    await inline_query.answer(
        results=results,
        cache_time=300,
        is_personal=False
    )


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
        return ""

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
