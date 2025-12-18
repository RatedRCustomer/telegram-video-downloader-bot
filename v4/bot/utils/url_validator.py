"""
URL validation and platform detection utilities
"""

import re
from urllib.parse import urlparse
from typing import Optional

# Supported domains
SUPPORTED_DOMAINS = {
    'youtube': ['youtube.com', 'youtu.be', 'youtube-nocookie.com'],
    'instagram': ['instagram.com'],
    'tiktok': ['tiktok.com', 'vm.tiktok.com'],
    'twitter': ['twitter.com', 'x.com'],
    'facebook': ['facebook.com', 'fb.watch', 'fb.com'],
    'reddit': ['reddit.com', 'v.redd.it', 'redd.it'],
    'threads': ['threads.net'],
    'twitch': ['twitch.tv'],
}

# URL patterns for each platform
URL_PATTERNS = {
    'youtube': [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+',
        r'youtube\.com/embed/[\w-]+',
        r'youtube-nocookie\.com/embed/[\w-]+',
    ],
    'instagram': [
        r'instagram\.com/(?:p|reel|reels|tv)/[\w-]+',
        r'instagram\.com/stories/[\w.]+/\d+',
    ],
    'tiktok': [
        r'(?:tiktok\.com/@[\w.]+/video/|vm\.tiktok\.com/)\w+',
        r'tiktok\.com/t/\w+',
    ],
    'twitter': [
        r'(?:twitter\.com|x\.com)/[\w]+/status/\d+',
    ],
    'facebook': [
        r'facebook\.com/[\w.]+/videos/\d+',
        r'facebook\.com/watch\?v=\d+',
        r'facebook\.com/reel/\d+',
        r'fb\.watch/[\w]+',
    ],
    'reddit': [
        r'reddit\.com/r/[\w]+/comments/[\w]+',
        r'v\.redd\.it/[\w]+',
    ],
    'threads': [
        r'threads\.net/@[\w.]+/post/[\w]+',
        r'threads\.net/t/[\w]+',
    ],
    'twitch': [
        r'twitch\.tv/[\w]+/clip/[\w-]+',
        r'clips\.twitch\.tv/[\w-]+',
    ],
}


def is_valid_video_url(url: str) -> bool:
    """
    Check if the URL is a valid video URL from a supported platform.
    """
    if not url:
        return False

    # Basic URL validation
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        if parsed.scheme not in ('http', 'https'):
            return False
    except Exception:
        return False

    # Check against supported domains
    domain = parsed.netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]

    for platform, domains in SUPPORTED_DOMAINS.items():
        if any(d in domain for d in domains):
            # Validate URL pattern
            for pattern in URL_PATTERNS.get(platform, []):
                if re.search(pattern, url, re.IGNORECASE):
                    return True

    return False


def detect_platform(url: str) -> str:
    """
    Detect the platform from a URL.
    Returns platform name or 'unknown'.
    """
    if not url:
        return 'unknown'

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
    except Exception:
        return 'unknown'

    for platform, domains in SUPPORTED_DOMAINS.items():
        if any(d in domain for d in domains):
            return platform

    return 'unknown'


def extract_video_id(url: str, platform: str) -> Optional[str]:
    """
    Extract video ID from URL for caching purposes.
    """
    patterns = {
        'youtube': r'(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})',
        'instagram': r'(?:p|reel|reels|tv)/([a-zA-Z0-9_-]+)',
        'tiktok': r'video/(\d+)',
        'twitter': r'status/(\d+)',
        'reddit': r'comments/([a-zA-Z0-9]+)',
        'twitch': r'clip/([a-zA-Z0-9_-]+)',
    }

    pattern = patterns.get(platform)
    if not pattern:
        return None

    match = re.search(pattern, url)
    return match.group(1) if match else None


def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent caching.
    Removes tracking parameters and normalizes format.
    """
    try:
        parsed = urlparse(url)
        # Remove tracking parameters
        # Keep only essential query parameters
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except Exception:
        return url
