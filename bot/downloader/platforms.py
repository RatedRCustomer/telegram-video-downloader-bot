import logging
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse
import re


log = logging.getLogger(__name__)


class Platform(str, Enum):
    YOUTUBE = "youtube"
    YOUTUBE_MUSIC = "youtube_music"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    TWITTER = "twitter"
    PINTEREST = "pinterest"
    THREADS = "threads"
    SOUNDCLOUD = "soundcloud"
    SPOTIFY = "spotify"
    DEEZER = "deezer"


class MediaType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class DownloadTool(str, Enum):
    YTDLP = "yt-dlp"
    SPOTDL = "spotdl"
    GALLERY_DL = "gallery-dl"


@dataclass(frozen=True)
class PlatformMatch:
    platform: Platform
    media_type: MediaType
    tool: DownloadTool
    url: str


_DOMAIN_MAP: dict[str, Platform] = {
    "youtube.com": Platform.YOUTUBE,
    "www.youtube.com": Platform.YOUTUBE,
    "m.youtube.com": Platform.YOUTUBE,
    "youtu.be": Platform.YOUTUBE,
    "music.youtube.com": Platform.YOUTUBE_MUSIC,
    "instagram.com": Platform.INSTAGRAM,
    "www.instagram.com": Platform.INSTAGRAM,
    "tiktok.com": Platform.TIKTOK,
    "www.tiktok.com": Platform.TIKTOK,
    "twitter.com": Platform.TWITTER,
    "x.com": Platform.TWITTER,
    "www.x.com": Platform.TWITTER,
    "pinterest.com": Platform.PINTEREST,
    "www.pinterest.com": Platform.PINTEREST,
    "pin.it": Platform.PINTEREST,
    "threads.net": Platform.THREADS,
    "www.threads.net": Platform.THREADS,
    "threads.com": Platform.THREADS,
    "www.threads.com": Platform.THREADS,
    "soundcloud.com": Platform.SOUNDCLOUD,
    "m.soundcloud.com": Platform.SOUNDCLOUD,
    "open.spotify.com": Platform.SPOTIFY,
    "deezer.com": Platform.DEEZER,
    "www.deezer.com": Platform.DEEZER,
}

_SHORT_URL_DOMAINS: frozenset[str] = frozenset({
    "vm.tiktok.com",
    "vt.tiktok.com",
    "t.co",
    "pin.it",
    "spotify.link",
    "deezer.page.link",
    "link.deezer.com",
    "on.soundcloud.com",
})

_AUDIO_PLATFORMS: frozenset[Platform] = frozenset({
    Platform.YOUTUBE_MUSIC,
    Platform.SPOTIFY,
    Platform.DEEZER,
    Platform.SOUNDCLOUD,
})

_PLATFORM_TOOLS: dict[Platform, DownloadTool] = {
    Platform.YOUTUBE: DownloadTool.YTDLP,
    Platform.YOUTUBE_MUSIC: DownloadTool.YTDLP,
    Platform.INSTAGRAM: DownloadTool.YTDLP,
    Platform.TIKTOK: DownloadTool.YTDLP,
    Platform.TWITTER: DownloadTool.YTDLP,
    Platform.THREADS: DownloadTool.YTDLP,
    Platform.SOUNDCLOUD: DownloadTool.YTDLP,
    Platform.PINTEREST: DownloadTool.GALLERY_DL,
    Platform.SPOTIFY: DownloadTool.YTDLP,
    Platform.DEEZER: DownloadTool.YTDLP,
}

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(text)


def identify_platform(url: str) -> PlatformMatch | None:
    parsed = urlparse(url)
    domain = parsed.hostname
    if not domain:
        return None

    platform = _DOMAIN_MAP.get(domain)
    if platform is None:
        return None

    media_type = MediaType.AUDIO if platform in _AUDIO_PLATFORMS else MediaType.VIDEO
    tool = _PLATFORM_TOOLS[platform]

    return PlatformMatch(platform=platform, media_type=media_type, tool=tool, url=url)


def is_short_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in _SHORT_URL_DOMAINS if parsed.hostname else False


async def resolve_short_url(url: str) -> str | None:
    """Resolve a shortened URL to its final destination."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return str(resp.url)
    except Exception as e:
        log.warning("Failed to resolve short URL %s: %s", url, e)
        return None
