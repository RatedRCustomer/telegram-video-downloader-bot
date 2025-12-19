"""
Command handlers for the bot
/start, /help, /stats, /settings
"""

import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from keyboards.main import get_main_keyboard, get_settings_keyboard

router = Router(name="commands")
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command"""
    user = message.from_user

    welcome_text = f"""
👋 <b>Привіт, {user.first_name}!</b>

Я бот для завантаження відео з популярних платформ.

<b>🎬 Підтримувані платформи:</b>
• YouTube, YouTube Shorts
• Instagram (Reels, Stories, Posts)
• TikTok
• Twitter/X
• Facebook
• Reddit
• Threads (Meta)
• Twitch Clips

<b>📝 Як користуватися:</b>
1️⃣ Надішліть посилання на відео
2️⃣ Виберіть якість (або авто)
3️⃣ Отримайте відео!

<b>🔧 Команди:</b>
/help - Довідка
/stats - Ваша статистика
/settings - Налаштування

<b>💡 Inline режим:</b>
Напишіть @botname URL в будь-якому чаті
"""

    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard()
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    help_text = """
<b>📖 Довідка</b>

<b>Завантаження відео:</b>
Просто надішліть посилання на відео з підтримуваної платформи.

<b>Вибір якості:</b>
• <b>Авто</b> - найкраща якість до 50MB
• <b>1080p</b> - Full HD
• <b>720p</b> - HD (рекомендовано)
• <b>480p</b> - SD
• <b>360p</b> - Низька якість

<b>Особливості:</b>
• 🎵 Для YouTube можна завантажити тільки аудіо
• 📱 Instagram потребує cookies для Stories
• ⏱ Максимальна тривалість: 30 хвилин

<b>Inline режим:</b>
В будь-якому чаті напишіть:
<code>@botname https://youtube.com/watch?v=...</code>

<b>Проблеми?</b>
Якщо відео не завантажується:
1. Перевірте чи правильне посилання
2. Спробуйте іншу якість
3. Відео може бути приватним

<b>Ліміти:</b>
• 10 запитів на хвилину
• Файли до 50MB
"""

    await message.answer(help_text)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Handle /stats command - show user statistics"""
    user_id = message.from_user.id

    # Get stats from Redis/DB
    redis = message.bot.get("redis")

    if redis:
        stats = await redis.get_cached(f"user_stats:{user_id}")
    else:
        stats = None

    if stats:
        stats_text = f"""
<b>📊 Ваша статистика</b>

📥 Завантажено відео: <b>{stats.get('downloads', 0)}</b>
📦 Загальний розмір: <b>{stats.get('total_size_mb', 0):.1f} MB</b>
⏱ Середній час: <b>{stats.get('avg_time_sec', 0):.1f} сек</b>

<b>По платформах:</b>
• YouTube: {stats.get('youtube', 0)}
• Instagram: {stats.get('instagram', 0)}
• TikTok: {stats.get('tiktok', 0)}
• Twitter: {stats.get('twitter', 0)}
• Інші: {stats.get('other', 0)}

<b>Улюблена якість:</b> {stats.get('favorite_quality', '720p')}
"""
    else:
        stats_text = """
<b>📊 Ваша статистика</b>

У вас ще немає завантажень.
Надішліть посилання на відео, щоб почати!
"""

    await message.answer(stats_text)


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Handle /settings command"""
    settings_text = """
<b>⚙️ Налаштування</b>

Виберіть опцію для зміни:
"""

    await message.answer(
        settings_text,
        reply_markup=get_settings_keyboard()
    )


@router.message(Command("audio"))
async def cmd_audio(message: Message):
    """Handle /audio command - download audio from URL"""
    import asyncio
    from uuid import uuid4
    from celery import Celery
    from utils.url_validator import is_valid_url, detect_platform

    # Get URL from command arguments
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🎵 <b>Завантаження аудіо</b>\n\n"
            "Використання: <code>/audio URL</code>\n\n"
            "Приклад:\n"
            "<code>/audio https://youtube.com/watch?v=...</code>\n"
            "<code>/audio https://music.youtube.com/watch?v=...</code>"
        )
        return

    url = args[1].strip()

    if not is_valid_url(url):
        await message.answer("❌ Невірне або непідтримуване посилання")
        return

    platform = detect_platform(url)

    # Send processing message
    processing_msg = await message.reply(
        f"🎵 <b>Завантаження аудіо...</b>\n\n"
        f"🔗 Платформа: {platform.title()}\n"
        f"⏳ Прогрес: 0%"
    )

    # Get config and redis from dispatcher
    config = message.bot.get("config")
    redis = message.bot.get("redis")

    # Create download task
    download_id = str(uuid4())

    if redis:
        await redis.set_cached(
            f"download:{download_id}",
            {
                "user_id": message.from_user.id,
                "chat_id": message.chat.id,
                "message_id": processing_msg.message_id,
                "url": url,
                "platform": platform,
                "quality": "audio",
                "title": "Аудіо",
                "type": "audio",
            },
            ttl=3600
        )

    # Send task to Celery
    broker_url = config.celery_broker_url if config else 'redis://redis:6379/0'
    result_backend = config.celery_result_backend if config else 'redis://redis:6379/0'
    celery_app = Celery('tasks', broker=broker_url, backend=result_backend)

    celery_app.send_task(
        'tasks.download_video',
        args=[download_id, url, platform, 'best', 'audio'],
        queue='downloads'
    )

    logger.info(f"Audio download task {download_id} sent for {url}")

    # Import and start progress monitoring
    from handlers.callbacks import monitor_download_progress
    asyncio.create_task(
        monitor_download_progress(
            message.bot,
            redis,
            config,
            download_id,
            message.chat.id,
            processing_msg.message_id,
            "Аудіо",
            media_type="audio"
        )
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Handle /admin command - admin panel"""
    config = message.bot.get("config")

    if not config or message.from_user.id not in config.admin_ids:
        await message.answer("⛔️ Доступ заборонено")
        return

    admin_text = """
<b>🔧 Адмін панель</b>

/admin_stats - Загальна статистика
/admin_users - Список користувачів
/admin_broadcast - Розсилка
/admin_cache - Керування кешем
"""

    await message.answer(admin_text)
