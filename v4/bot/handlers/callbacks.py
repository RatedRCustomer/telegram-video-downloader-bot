"""
Callback query handlers for quality selection and download progress
"""

import logging
import asyncio
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from celery import Celery

router = Router(name="callbacks")
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("quality:"))
async def handle_quality_selection(callback: CallbackQuery):
    """Handle quality selection callback"""
    await callback.answer()

    # Parse callback data: quality:720p:msg_id
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ Невірні дані", show_alert=True)
        return

    quality = parts[1]
    msg_id = parts[2]

    redis = callback.bot.get("redis")
    config = callback.bot.get("config")

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
    video_info = url_data.get("info", {})

    # Update message to show downloading
    title = video_info.get("title", "Завантаження")[:50]
    await callback.message.edit_caption(
        caption=(
            f"⬇️ <b>Завантаження...</b>\n\n"
            f"📹 {title}\n"
            f"📊 Якість: {quality}\n"
            f"⏳ Прогрес: 0%"
        ),
        reply_markup=None
    ) if callback.message.photo else await callback.message.edit_text(
        f"⬇️ <b>Завантаження...</b>\n\n"
        f"📹 {title}\n"
        f"📊 Якість: {quality}\n"
        f"⏳ Прогрес: 0%"
    )

    # Create download task
    from uuid import uuid4
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
            },
            ttl=3600
        )

    # Send task to Celery
    celery_app = Celery(
        'tasks',
        broker=config.celery_broker_url,
        backend=config.celery_result_backend
    )

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
            download_id,
            callback.message.chat.id,
            callback.message.message_id,
            title
        )
    )


@router.callback_query(F.data.startswith("audio:"))
async def handle_audio_download(callback: CallbackQuery):
    """Handle audio-only download for YouTube"""
    await callback.answer()

    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("❌ Невірні дані", show_alert=True)
        return

    msg_id = parts[1]

    redis = callback.bot.get("redis")
    config = callback.bot.get("config")

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
    video_info = url_data.get("info", {})
    title = video_info.get("title", "Завантаження")[:50]

    # Update message
    await callback.message.edit_caption(
        caption=(
            f"🎵 <b>Завантаження аудіо...</b>\n\n"
            f"🎧 {title}\n"
            f"⏳ Прогрес: 0%"
        ),
        reply_markup=None
    ) if callback.message.photo else await callback.message.edit_text(
        f"🎵 <b>Завантаження аудіо...</b>\n\n"
        f"🎧 {title}\n"
        f"⏳ Прогрес: 0%"
    )

    # Create download task
    from uuid import uuid4
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
            },
            ttl=3600
        )

    # Send task to Celery
    celery_app = Celery(
        'tasks',
        broker=config.celery_broker_url,
        backend=config.celery_result_backend
    )

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
            download_id,
            callback.message.chat.id,
            callback.message.message_id,
            title,
            is_audio=True
        )
    )


@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery):
    """Handle cancel button"""
    await callback.answer("❌ Скасовано")
    await callback.message.delete()


@router.callback_query(F.data.startswith("settings:"))
async def handle_settings(callback: CallbackQuery):
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


async def monitor_download_progress(
    bot,
    redis,
    download_id: str,
    chat_id: int,
    message_id: int,
    title: str,
    is_audio: bool = False
):
    """Monitor download progress and update message"""
    last_progress = 0
    max_wait = 300  # 5 minutes timeout
    wait_time = 0

    icon = "🎵" if is_audio else "📹"
    action = "аудіо" if is_audio else "відео"

    while wait_time < max_wait:
        await asyncio.sleep(2)
        wait_time += 2

        if not redis:
            continue

        progress_data = await redis.get_progress(download_id)

        if not progress_data:
            continue

        status = progress_data.get("status")
        progress = progress_data.get("progress", 0)

        if status == "completed":
            # Download completed - file will be sent by worker via upload task
            return

        if status == "failed":
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
            progress_bar = create_progress_bar(progress)

            try:
                await bot.edit_message_text(
                    f"⬇️ <b>Завантаження {action}...</b>\n\n"
                    f"{icon} {title}\n\n"
                    f"{progress_bar} {progress}%",
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
