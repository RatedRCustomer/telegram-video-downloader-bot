"""
Configuration for Video Bot v4.0
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    # Telegram
    bot_token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    webhook_url: Optional[str] = os.getenv('WEBHOOK_URL')
    webhook_path: str = os.getenv('WEBHOOK_PATH', '/webhook')
    webhook_port: int = int(os.getenv('WEBHOOK_PORT', '8443'))

    # Redis
    redis_url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # PostgreSQL
    database_url: str = os.getenv('DATABASE_URL', 'postgresql://videobot:videobot@localhost:5432/videobot')

    # MinIO
    minio_endpoint: str = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
    minio_access_key: str = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
    minio_secret_key: str = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
    minio_bucket: str = os.getenv('MINIO_BUCKET', 'videos')
    minio_secure: bool = os.getenv('MINIO_SECURE', 'false').lower() == 'true'

    # Limits
    max_file_size: int = int(os.getenv('MAX_FILE_SIZE', 50_000_000))  # 50MB
    rate_limit_user: int = int(os.getenv('RATE_LIMIT_USER', 30))  # seconds
    rate_limit_group: int = int(os.getenv('RATE_LIMIT_GROUP', 10))  # seconds

    # Paths
    download_path: str = os.getenv('DOWNLOAD_PATH', '/downloads')
    cookies_path: str = os.getenv('COOKIES_PATH', '/cookies/cookies.txt')

    # Cache TTL
    cache_ttl: int = int(os.getenv('CACHE_TTL', 86400 * 7))  # 7 days
    info_cache_ttl: int = int(os.getenv('INFO_CACHE_TTL', 3600))  # 1 hour


config = Config()


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
