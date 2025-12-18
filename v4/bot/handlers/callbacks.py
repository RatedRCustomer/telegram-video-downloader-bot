"""
Callback query handlers for quality selection, media downloads, and progress
"""

import logging
import asyncio
from uuid import uuid4

from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest

from celery import Celery

router = Router(name="callbacks")
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("quality:"))
async def handle_quality_selection(callback: CallbackQuery):
    """Handle quality selection callback for video downloads"""
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
    media_info = url_data.get("info", {})

    # Update message to show downloading
    title = media_info.get("title", "Завантаження")[:50]
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
    media_info = url_data.get("info", {})
    title = media_info.get("title", "Завантаження")[:50]

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
async def handle_media_download(callback: CallbackQuery):
    """Handle photo/media download callbacks"""
    await callback.answer()

    # Parse callback data: media:action:msg_id
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ Невірні дані", show_alert=True)
        return

    action = parts[1]  # all, photo, caption
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
    media_info = url_data.get("info", {})
    is_carousel = url_data.get("is_carousel", False)

    title = media_info.get("title", "Пост")[:50]
    description = media_info.get("description", "")
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
async def handle_cancel(callback: CallbackQuery):
    """Handle cancel button"""
    await callback.answer("❌ Скасовано")
    try:
        await callback.message.delete()
    except:
        pass


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
            # Get download info to retrieve files
            download_info = await redis.get_cached(f"download:{download_id}")

            # Get result from Celery
            celery_app = get_celery_app(config)
            result = celery_app.AsyncResult(download_id)

            try:
                # Try to get result if available
                task_result = result.get(timeout=5)
            except:
                task_result = None

            # Send files to user
            await send_completed_media(
                bot,
                chat_id,
                message_id,
                download_info,
                task_result,
                media_type,
                include_caption,
                description
            )
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


async def send_completed_media(
    bot,
    chat_id: int,
    message_id: int,
    download_info: dict,
    task_result: dict,
    media_type: str,
    include_caption: bool,
    description: str
):
    """Send completed media to user"""
    if not task_result or task_result.get('status') == 'error':
        error_msg = task_result.get('error', 'Невідома помилка') if task_result else 'Невідома помилка'
        try:
            await bot.edit_message_text(
                f"❌ <b>Помилка</b>\n\n{error_msg}",
                chat_id=chat_id,
                message_id=message_id
            )
        except:
            pass
        return

    # Build caption with blockquote if requested
    caption = ""
    if include_caption and description:
        # Use HTML blockquote for caption
        caption = f"<blockquote>{description[:900]}</blockquote>"

        if task_result.get('uploader'):
            caption += f"\n\n👤 {task_result['uploader']}"

    # Delete progress message
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

    # Send media based on type
    if media_type == "media" and task_result.get('media'):
        # Send photos/media
        media_files = task_result['media']

        if len(media_files) == 1:
            # Single file
            file_info = media_files[0]
            if file_info['type'] == 'photo':
                # For now, send the file key info (actual file sending requires MinIO integration)
                await bot.send_message(
                    chat_id,
                    f"✅ <b>Фото завантажено</b>\n\n"
                    f"📁 Файл: {file_info.get('file_key', 'N/A')}\n"
                    f"📊 Розмір: {format_size(file_info.get('file_size', 0))}"
                    + (f"\n\n{caption}" if caption else "")
                )
            else:
                await bot.send_message(
                    chat_id,
                    f"✅ <b>Відео завантажено</b>\n\n"
                    f"📁 Файл: {file_info.get('file_key', 'N/A')}\n"
                    f"📊 Розмір: {format_size(file_info.get('file_size', 0))}"
                    + (f"\n\n{caption}" if caption else "")
                )
        else:
            # Multiple files (carousel)
            files_text = "\n".join([
                f"  • {f.get('type', 'file')}: {format_size(f.get('file_size', 0))}"
                for f in media_files
            ])
            await bot.send_message(
                chat_id,
                f"✅ <b>Карусель завантажено</b>\n\n"
                f"📁 Файли ({len(media_files)}):\n{files_text}"
                + (f"\n\n{caption}" if caption else "")
            )
    else:
        # Video or audio
        file_key = task_result.get('file_key', '')
        file_size = task_result.get('file_size', 0)
        title = task_result.get('title', 'Медіа')

        await bot.send_message(
            chat_id,
            f"✅ <b>{'Аудіо' if media_type == 'audio' else 'Відео'} завантажено</b>\n\n"
            f"📹 {title}\n"
            f"📁 Файл: {file_key}\n"
            f"📊 Розмір: {format_size(file_size)}"
            + (f"\n\n{caption}" if caption else "")
        )


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
