import logging
import os
from pathlib import Path

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.db import Database

log = logging.getLogger(__name__)

router = Router()

_PLATFORMS = (
    "YouTube / Shorts / YouTube Music",
    "Instagram (Reels, Stories, Posts)",
    "TikTok",
    "X (Twitter)",
    "Pinterest",
    "Threads",
    "VK / VK Video",
    "SoundCloud",
    "Spotify",
    "Deezer",
)

_COOKIES_MAX_BYTES = 500_000  # cookies.txt > 500KB ~ заведено забагато / помилка експорту

_START_TEXT = (
    "\U0001f44b Привіт! Я завантажую "
    "відео та музику з популярних "
    "платформ.\n\n"
    "Просто кинь посилання "
    "\u2014 я завантажу автоматично.\n\n"
    "\U0001f4cb Підтримувані платформи:\n"
    + "\n".join(f"  \u2022 {p}" for p in _PLATFORMS)
    + "\n\n"
    "Для вибору якості: /quality &lt;посилання&gt;"
)

_HELP_TEXT = (
    "\u2139\ufe0f <b>Як користуватись:</b>\n\n"
    "1. Кинь посилання \u2014 "
    "я завантажу в найкращій "
    "якості (до 50 МБ)\n"
    "2. <code>/quality посилання</code> \u2014 "
    "вибери якість вручну\n"
    "3. <code>/stats</code> \u2014 "
    "твоя статистика завантажень\n\n"
    "<b>Музичні сервіси</b> "
    "(Spotify, Deezer, SoundCloud, YouTube Music) \u2014 "
    "завжди завантажую як MP3.\n\n"
    "<b>У групі</b> \u2014 "
    "просто кинь посилання, "
    "я відреагую. "
    "Або тегни мене з будь-яким посиланням."
)


def _format_bytes(n: int) -> str:
    if n < 1_000_000:
        return f"{n / 1000:.1f} KB"
    if n < 1_000_000_000:
        return f"{n / 1_000_000:.1f} MB"
    return f"{n / 1_000_000_000:.2f} GB"


def setup_command_handlers(config: Config, db: Database):
    @router.message(Command("start"))
    async def cmd_start(message: Message):
        await message.reply(_START_TEXT)

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        await message.reply(_HELP_TEXT)

    @router.message(Command("stats"))
    async def cmd_stats(message: Message):
        if not message.from_user:
            return
        stats = await db.get_user_stats(message.from_user.id)
        total = stats["total_downloads"]
        if total == 0:
            await message.reply(
                "\U0001f4ca Ти ще нічого "
                "не завантажував."
            )
            return

        lines = [
            "\U0001f4ca <b>Твоя статистика:</b>\n",
            f"Всього завантажень: <b>{total}</b>",
            f"Трафік: <b>{_format_bytes(stats['total_bytes'])}</b>\n",
        ]
        if stats["platforms"]:
            lines.append("По платформах:")
            for platform, count in sorted(
                stats["platforms"].items(), key=lambda x: -x[1]
            ):
                lines.append(f"  \u2022 {platform}: {count}")

        await message.reply("\n".join(lines))

    @router.message(Command("admin"))
    async def cmd_admin(message: Message):
        if not message.from_user:
            return
        if config.admin_ids and message.from_user.id not in config.admin_ids:
            return

        stats = await db.get_global_stats()

        lines = [
            "\U0001f4ca <b>Admin статистика:</b>\n",
            f"Всього завантажень: <b>{stats['total_downloads']}</b>",
            f"Трафік: <b>{_format_bytes(stats['total_bytes'])}</b>",
            f"Записів в кеші: <b>{stats['cache_entries']}</b>",
        ]

        # DB file size
        try:
            db_size = os.path.getsize(config.db_path)
            lines.append(f"Розмір БД: <b>{_format_bytes(db_size)}</b>")
        except Exception:
            pass

        if stats["top_users"]:
            lines.append("\n<b>Top користувачі:</b>")
            for i, (uid, uname, cnt) in enumerate(stats["top_users"], 1):
                name = f"@{uname}" if uname else f"id:{uid}"
                lines.append(f"  {i}. {name} \u2014 {cnt}")

        if stats["platforms"]:
            lines.append("\n<b>По платформах:</b>")
            for platform, count in sorted(
                stats["platforms"].items(), key=lambda x: -x[1]
            ):
                lines.append(f"  \u2022 {platform}: {count}")

        await message.reply("\n".join(lines))

    @router.message(Command("cookies"))
    async def cmd_cookies(message: Message, bot: Bot):
        # Admin-only, accepts an attached cookies.txt and writes to config.cookies_file.
        # Use case: yt-dlp cookies expire (YouTube/Instagram/etc.) — admin reuploads via TG.
        if not message.from_user:
            return
        if config.admin_ids and message.from_user.id not in config.admin_ids:
            return
        if not config.cookies_file:
            await message.reply(
                "⚠️ COOKIES_FILE не налаштовано в .env"
            )
            return

        doc = message.document
        if not doc:
            await message.reply(
                "\U0001f4ce Прикріпи <code>cookies.txt</code> з підписом "
                "<code>/cookies</code>\n\n"
                "Експорт з браузера: розширення "
                "<i>Get cookies.txt LOCALLY</i> "
                "(Chrome/Firefox).\n"
                "Формат: Netscape HTTP Cookie File."
            )
            return
        if not (doc.file_name and doc.file_name.lower().endswith(".txt")):
            await message.reply("⚠️ Очікую .txt файл")
            return
        if doc.file_size and doc.file_size > _COOKIES_MAX_BYTES:
            await message.reply(
                f"⚠️ Файл завеликий "
                f"({doc.file_size} > {_COOKIES_MAX_BYTES} B)"
            )
            return

        target = Path(config.cookies_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            await bot.download(doc, destination=target)
        except Exception as e:
            log.exception("Cookies download failed")
            await message.reply(f"❌ Не вдалось завантажити: {e}")
            return

        try:
            head = target.read_text(errors="replace")[:200]
        except Exception as e:
            await message.reply(f"❌ Не вдалось прочитати: {e}")
            return

        if "Netscape HTTP Cookie File" not in head:
            await message.reply(
                "⚠️ Це не схоже на Netscape cookies "
                "(немає header'а). "
                "Файл збережено, але yt-dlp може його відкинути."
            )
            return

        size = target.stat().st_size
        log.info(
            "Cookies updated by admin %s, %d bytes",
            message.from_user.id, size,
        )
        await message.reply(
            f"✅ Cookies оновлено: <b>{size}</b> байт"
        )

    return router
