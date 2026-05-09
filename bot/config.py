from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: list[int] = field(default_factory=list)
    max_concurrent_downloads: int = 2
    max_file_size: int = 50_000_000
    rate_limit_per_minute: int = 5
    download_dir: str = "/app/data/downloads"
    db_path: str = "/app/data/bot.db"
    cleanup_interval_hours: int = 1
    cache_ttl_days: int = 30
    audio_bitrate: int = 192
    cookies_file: str = ""
    cobalt_api_url: str = "http://cobalt:9000"
    log_level: str = "INFO"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN environment variable is required")

    raw_admins = os.getenv("ADMIN_IDS", "").strip()
    admin_ids = (
        [int(x) for x in raw_admins.split(",") if x.strip()]
        if raw_admins
        else []
    )

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        max_concurrent_downloads=int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2")),
        max_file_size=int(os.getenv("MAX_FILE_SIZE", "50000000")),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "5")),
        download_dir=os.getenv("DOWNLOAD_DIR", "/app/data/downloads"),
        db_path=os.getenv("DB_PATH", "/app/data/bot.db"),
        cleanup_interval_hours=int(os.getenv("CLEANUP_INTERVAL_HOURS", "1")),
        cache_ttl_days=int(os.getenv("CACHE_TTL_DAYS", "30")),
        audio_bitrate=int(os.getenv("AUDIO_BITRATE", "192")),
        cookies_file=os.getenv("COOKIES_FILE", ""),
        cobalt_api_url=os.getenv("COBALT_API_URL", "http://cobalt:9000"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
