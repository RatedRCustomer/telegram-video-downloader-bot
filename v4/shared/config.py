"""
Configuration for Video Bot v4.0
"""
import os
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Config:
    # Telegram
    bot_token: str = field(default_factory=lambda: os.getenv('TELEGRAM_BOT_TOKEN', ''))
    webhook_url: Optional[str] = field(default_factory=lambda: os.getenv('WEBHOOK_URL'))
    webhook_path: str = field(default_factory=lambda: os.getenv('WEBHOOK_PATH', '/webhook'))
    webhook_port: int = field(default_factory=lambda: int(os.getenv('WEBHOOK_PORT', '8443')))
    admin_ids: List[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip().isdigit()
    ])

    # Redis
    redis_url: str = field(default_factory=lambda: os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    celery_broker_url: str = field(default_factory=lambda: os.getenv('CELERY_BROKER_URL', os.getenv('REDIS_URL', 'redis://localhost:6379/0')))
    celery_result_backend: str = field(default_factory=lambda: os.getenv('CELERY_RESULT_BACKEND', os.getenv('REDIS_URL', 'redis://localhost:6379/0')))

    # PostgreSQL
    database_url: str = field(default_factory=lambda: os.getenv('DATABASE_URL', 'postgresql://videobot:videobot@localhost:5432/videobot'))

    # MinIO
    minio_endpoint: str = field(default_factory=lambda: os.getenv('MINIO_ENDPOINT', 'localhost:9000'))
    minio_access_key: str = field(default_factory=lambda: os.getenv('MINIO_ACCESS_KEY', 'minioadmin'))
    minio_secret_key: str = field(default_factory=lambda: os.getenv('MINIO_SECRET_KEY', 'minioadmin123'))
    minio_bucket: str = field(default_factory=lambda: os.getenv('MINIO_BUCKET', 'videos'))
    minio_secure: bool = field(default_factory=lambda: os.getenv('MINIO_SECURE', 'false').lower() == 'true')

    # yt-dlp service
    ytdlp_service_url: str = field(default_factory=lambda: os.getenv('YTDLP_SERVICE_URL', 'http://yt-dlp-api:8081'))

    # Limits
    max_file_size: int = field(default_factory=lambda: int(os.getenv('MAX_FILE_SIZE', '50000000')))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv('RATE_LIMIT_PER_MINUTE', '10')))
    rate_limit_user: int = field(default_factory=lambda: int(os.getenv('RATE_LIMIT_USER', '30')))
    rate_limit_group: int = field(default_factory=lambda: int(os.getenv('RATE_LIMIT_GROUP', '10')))

    # Paths
    download_path: str = field(default_factory=lambda: os.getenv('DOWNLOAD_PATH', '/downloads'))
    cookies_path: str = field(default_factory=lambda: os.getenv('COOKIES_PATH', '/cookies/cookies.txt'))

    # Cache TTL
    cache_ttl: int = field(default_factory=lambda: int(os.getenv('CACHE_TTL', str(86400 * 7))))
    info_cache_ttl: int = field(default_factory=lambda: int(os.getenv('INFO_CACHE_TTL', '3600')))


# Supported platforms
SUPPORTED_DOMAINS = [
    'tiktok.com', 'vm.tiktok.com',
    'instagram.com',
    'youtube.com', 'youtu.be',
    'twitter.com', 'x.com',
    'facebook.com', 'fb.watch',
    'reddit.com', 'redd.it',
    'pinterest.com', 'pin.it',
    'threads.net',
    'twitch.tv', 'clips.twitch.tv',
]


def detect_platform(url: str) -> str:
    """Detect platform from URL"""
    url_lower = url.lower()
    platform_map = {
        'tiktok.com': 'tiktok',
        'vm.tiktok.com': 'tiktok',
        'instagram.com': 'instagram',
        'youtube.com': 'youtube',
        'youtu.be': 'youtube',
        'twitter.com': 'twitter',
        'x.com': 'twitter',
        'facebook.com': 'facebook',
        'fb.watch': 'facebook',
        'reddit.com': 'reddit',
        'pinterest.com': 'pinterest',
        'pin.it': 'pinterest',
        'threads.net': 'threads',
        'twitch.tv': 'twitch',
        'clips.twitch.tv': 'twitch',
    }

    for domain, platform in platform_map.items():
        if domain in url_lower:
            return platform

    return 'unknown'
