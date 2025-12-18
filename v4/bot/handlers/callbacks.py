"""
Callback query handlers for quality selection, media downloads, and progress
"""

import logging
import asyncio
from uuid import uuid4
from typing import Any

from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest

from celery import Celery

router = Router(name="callbacks")
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("quality:"))
async def handle_quality_selection(callback: CallbackQuery, config: Any = None, redis: Any = None):
    """Handle quality selection callback for video downloads"""
    await callback.answer()

    # Parse callback data: quality:720p:msg_id
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ Невірні дані", show_alert=True)
        return

    quality = parts[1]
    msg_id = parts[2]

    # Get pending URL data
    cache_key = f"pending_url:{callback.from_user.id}:{msg_id}"
    url_data = None

    if redis:
        url_data = await redis.get_cached(cache_key)

    if not url_data:
        await callback.answer(
            "❌ Сесія закінчилася. Надішліть посилання ще раз.",
            show_alert=True
        )
        return

    url = url_data["url"]
    platform = url_data["platform"]
    media_info = url_data.get("info", {})

    # Update message to show downloading
    title = media_info.get("title", "Завантаження")[:50] if media_info else "Завантаження"
    await update_message(
        callback.message,
        f"⬇️ <b>Завантаження...</b>\n\n"
        f"📹 {title}\n"
        f"📊 Якість: {quality}\n"
        f"⏳ Прогрес: 0%"
    )

    # Create download task
    download_id = str(uuid4())

    # Store download info for progress tracking
    if redis:
        await redis.set_cached(
            f"download:{download_id}",
            {
                "user_id": callback.from_user.id,
                "chat_id": callback.message.chat.id,
                "message_id": callback.message.message_id,
                "url": url,
                "platform": platform,
                "quality": quality,
                "title": title,
                "type": "video",
            },
            ttl=3600
        )

    # Send task to Celery
    celery_app = get_celery_app(config)
    celery_app.send_task(
        'tasks.download_video',
        args=[download_id, url, platform, quality, 'video'],
        queue='downloads'
    )

    logger.info(f"Download task {download_id} sent for {url}")

    # Start progress monitoring
    asyncio.create_task(
        monitor_download_progress(
            callback.bot,
            redis,
            config,
            download_id,
            callback.message.chat.id,
            callback.message.message_id,
            title,
            media_type="video"
        )
    )


@router.callback_query(F.data.startswith("audio:"))
async def handle_audio_download(callback: CallbackQuery, config: Any = None, redis: Any = None):
    """Handle audio-only download for YouTube"""
    await callback.answer()

    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("❌ Невірні дані", show_alert=True)
        return

    msg_id = parts[1]

    # Get pending URL data
    cache_key = f"pending_url:{callback.from_user.id}:{msg_id}"
    url_data = None

    if redis:
        url_data = await redis.get_cached(cache_key)

    if not url_data:
        await callback.answer(
            "❌ Сесія закінчилася. Надішліть посилання ще раз.",
            show_alert=True
        )
        return

    url = url_data["url"]
    platform = url_data["platform"]
    media_info = url_data.get("info", {})
    title = media_info.get("title", "Завантаження")[:50] if media_info else "Завантаження"

    # Update message
    await update_message(
        callback.message,
        f"🎵 <b>Завантаження аудіо...</b>\n\n"
        f"🎧 {title}\n"
        f"⏳ Прогрес: 0%"
    )

    # Create download task
    download_id = str(uuid4())

    if redis:
        await redis.set_cached(
            f"download:{download_id}",
            {
                "user_id": callback.from_user.id,
                "chat_id": callback.message.chat.id,
                "message_id": callback.message.message_id,
                "url": url,
                "platform": platform,
                "quality": "audio",
                "title": title,
                "type": "audio",
            },
            ttl=3600
        )

    # Send task to Celery
    celery_app = get_celery_app(config)
    celery_app.send_task(
        'tasks.download_video',
        args=[download_id, url, platform, 'best', 'audio'],
        queue='downloads'
    )

    # Start progress monitoring
    asyncio.create_task(
        monitor_download_progress(
            callback.bot,
            redis,
            config,
            download_id,
            callback.message.chat.id,
            callback.message.message_id,
            title,
            media_type="audio"
        )
    )


@router.callback_query(F.data.startswith("media:"))
async def handle_media_download(callback: CallbackQuery, config: Any = None, redis: Any = None):
    """Handle photo/media download callbacks"""
    await callback.answer()

    # Parse callback data: media:action:msg_id
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ Невірні дані", show_alert=True)
        return

    action = parts[1]  # all, photo, caption
    msg_id = parts[2]

    # Get pending URL data
    cache_key = f"pending_url:{callback.from_user.id}:{msg_id}"
    url_data = None

    if redis:
        url_data = await redis.get_cached(cache_key)

    if not url_data:
        await callback.answer(
            "❌ Сесія закінчилася. Надішліть посилання ще раз.",
            show_alert=True
        )
        return

    url = url_data["url"]
    platform = url_data["platform"]
    media_info = url_data.get("info", {})
    is_carousel = url_data.get("is_carousel", False)

    title = media_info.get("title", "Пост")[:50] if media_info else "Пост"
    description = media_info.get("description", "") if media_info else ""
    include_caption = action == "caption"

    # Update message
    if is_carousel:
        await update_message(
            callback.message,
            f"🖼 <b>Завантаження каруселі...</b>\n\n"
            f"📌 {title}\n"
            f"⏳ Прогрес: 0%"
        )
    else:
        await update_message(
            callback.message,
            f"🖼 <b>Завантаження фото...</b>\n\n"
            f"📌 {title}\n"
            f"⏳ Прогрес: 0%"
        )

    # Create download task
    download_id = str(uuid4())

    if redis:
        await redis.set_cached(
            f"download:{download_id}",
            {
                "user_id": callback.from_user.id,
                "chat_id": callback.message.chat.id,
                "message_id": callback.message.message_id,
                "url": url,
                "platform": platform,
                "title": title,
                "description": description,
                "include_caption": include_caption,
                "type": "media",
                "is_carousel": is_carousel,
            },
            ttl=3600
        )

    # Send task to Celery
    celery_app = get_celery_app(config)
    celery_app.send_task(
        'tasks.download_media',
        args=[download_id, url, platform],
        queue='downloads'
    )

    logger.info(f"Media download task {download_id} sent for {url}")

    # Start progress monitoring
    asyncio.create_task(
        monitor_download_progress(
            callback.bot,
            redis,
            config,
            download_id,
            callback.message.chat.id,
            callback.message.message_id,
            title,
            media_type="media",
            include_caption=include_caption,
            description=description
        )
    )


@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, **kwargs):
    """Handle cancel button"""
    await callback.answer("❌ Скасовано")
    try:
        await callback.message.delete()
    except:
        pass


@router.callback_query(F.data.startswith("settings:"))
async def handle_settings(callback: CallbackQuery, **kwargs):
    """Handle settings callbacks"""
    await callback.answer()

    action = callback.data.split(":")[1]

    if action == "quality":
        from keyboards.quality import get_default_quality_keyboard
        await callback.message.edit_text(
            "<b>⚙️ Якість за замовчуванням</b>\n\n"
            "Виберіть якість, яка буде використовуватися автоматично:",
            reply_markup=get_default_quality_keyboard()
        )
    elif action == "notifications":
        await callback.message.edit_text(
            "<b>🔔 Сповіщення</b>\n\n"
            "Ця функція в розробці.",
            reply_markup=None
        )


def get_celery_app(config):
    """Get Celery app instance"""
    broker_url = config.celery_broker_url if config else 'redis://redis:6379/0'
    result_backend = config.celery_result_backend if config else 'redis://redis:6379/0'
    return Celery('tasks', broker=broker_url, backend=result_backend)


async def update_message(message, text: str):
    """Update message text or caption depending on message type"""
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=None)
        else:
            await message.edit_text(text, reply_markup=None)
    except TelegramBadRequest:
        pass


async def monitor_download_progress(
    bot,
    redis,
    config,
    download_id: str,
    chat_id: int,
    message_id: int,
    title: str,
    media_type: str = "video",
    include_caption: bool = False,
    description: str = ""
):
    """Monitor download progress and update message"""
    last_progress = 0
    max_wait = 300  # 5 minutes timeout
    wait_time = 0

    icons = {
        "video": "📹",
        "audio": "🎵",
        "media": "🖼",
    }
    icon = icons.get(media_type, "📎")

    while wait_time < max_wait:
        await asyncio.sleep(2)
        wait_time += 2

        if not redis:
            continue

        progress_data = await redis.get_progress(download_id)

        if not progress_data:
            continue

        status = progress_data.get("status")
        progress = float(progress_data.get("progress", 0))

        if status == "completed":
            # Download completed
            try:
                await bot.edit_message_text(
                    f"✅ <b>Завантаження завершено!</b>\n\n"
                    f"{icon} {title}",
                    chat_id=chat_id,
                    message_id=message_id
                )
            except:
                pass
            return

        if status == "error":
            error = progress_data.get("error", "Невідома помилка")
            try:
                await bot.edit_message_text(
                    f"❌ <b>Помилка завантаження</b>\n\n"
                    f"{icon} {title}\n"
                    f"💬 {error}",
                    chat_id=chat_id,
                    message_id=message_id
                )
            except TelegramBadRequest:
                pass
            return

        # Update progress if changed significantly
        if progress > last_progress + 5:
            last_progress = progress
            progress_bar = create_progress_bar(int(progress))

            try:
                await bot.edit_message_text(
                    f"⬇️ <b>Завантаження...</b>\n\n"
                    f"{icon} {title}\n\n"
                    f"{progress_bar} {int(progress)}%",
                    chat_id=chat_id,
                    message_id=message_id
                )
            except TelegramBadRequest:
                pass

    # Timeout
    try:
        await bot.edit_message_text(
            f"⏱ <b>Таймаут</b>\n\n"
            f"{icon} {title}\n"
            f"Завантаження зайняло занадто багато часу.",
            chat_id=chat_id,
            message_id=message_id
        )
    except TelegramBadRequest:
        pass


def create_progress_bar(progress: int, length: int = 10) -> str:
    """Create a text progress bar"""
    filled = int(length * progress / 100)
    empty = length - filled
    return "▓" * filled + "░" * empty


def format_size(size_bytes: int) -> str:
    """Format file size to human readable"""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"
