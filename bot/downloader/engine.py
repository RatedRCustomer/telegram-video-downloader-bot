import asyncio
import hashlib
import html
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiohttp

from bot.config import Config
from bot.downloader.platforms import (
    DownloadTool,
    MediaType,
    Platform,
    PlatformMatch,
)

log = logging.getLogger(__name__)

# Platforms where Cobalt API is the preferred fallback
_COBALT_PLATFORMS = frozenset({
    Platform.INSTAGRAM, Platform.TIKTOK, Platform.TWITTER,
})


@dataclass
class DownloadResult:
    file_path: str
    title: str
    duration: int | None
    file_size: int
    media_type: MediaType
    platform: Platform


class DownloadEngine:
    def __init__(self, config: Config):
        self._cfg = config

    @staticmethod
    def url_hash(url: str, quality: str) -> str:
        raw = f"{url.strip().rstrip('/')}:{quality}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _unique_path(self, ext: str = ".mp4") -> str:
        """Generate a unique file path in the download directory."""
        return os.path.join(self._cfg.download_dir, f"{uuid.uuid4().hex[:12]}{ext}")

    async def download(
        self,
        match: PlatformMatch,
        quality: str = "auto",
        progress_cb=None,
    ) -> DownloadResult:
        # Audio platforms: Spotify, Deezer, SoundCloud, YT Music
        if match.platform in (Platform.SPOTIFY, Platform.DEEZER):
            return await self._run_music_search(match, progress_cb)

        if match.tool == DownloadTool.GALLERY_DL:
            try:
                return await self._run_gallery_dl(match, progress_cb)
            except Exception:
                return await self._try_cobalt(match, progress_cb)

        if match.media_type == MediaType.AUDIO:
            try:
                return await self._run_ytdlp(match, quality, progress_cb)
            except Exception:
                if match.platform in _COBALT_PLATFORMS:
                    return await self._try_cobalt(match, progress_cb)
                raise

        # Video: try yt-dlp with descending quality until file fits
        ytdlp_failed = False
        for q in self._quality_chain(quality):
            if ytdlp_failed:
                break
            try:
                result = await self._run_ytdlp(match, q, progress_cb)
                if result.file_size <= self._cfg.max_file_size:
                    return result
                log.info("File %d bytes > limit, trying lower quality", result.file_size)
                os.unlink(result.file_path)
            except Exception as e:
                log.warning("yt-dlp failed for %s: %s", match.url, e)
                ytdlp_failed = True

        # Fallback: Cobalt API for supported platforms
        if ytdlp_failed and match.platform in _COBALT_PLATFORMS:
            return await self._try_cobalt(match, progress_cb)

        if ytdlp_failed:
            raise RuntimeError(f"Download failed for {match.url}")

        raise ValueError("File too large for Telegram even at 480p")

    def _quality_chain(self, quality: str) -> list[str]:
        chain = {
            "auto": ["auto", "720", "480"],
            "1080": ["1080", "720", "480"],
            "720": ["720", "480"],
            "480": ["480"],
        }
        return chain.get(quality, ["auto", "720", "480"])

    # --- Cobalt API ---

    async def _try_cobalt(
        self, match: PlatformMatch, progress_cb=None,
    ) -> DownloadResult:
        if not self._cfg.cobalt_api_url:
            raise RuntimeError("Cobalt API not configured")
        log.info("Trying Cobalt API for %s", match.url)
        return await self._run_cobalt(match, progress_cb)

    async def _run_cobalt(
        self, match: PlatformMatch, progress_cb=None,
    ) -> DownloadResult:
        api_url = self._cfg.cobalt_api_url.rstrip("/")
        payload = {
            "url": match.url,
            "videoQuality": "1080",
            "audioFormat": "mp3",
        }
        if match.media_type == MediaType.AUDIO:
            payload["downloadMode"] = "audio"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()

        status = data.get("status")
        if status == "error":
            error_code = data.get("error", {}).get("code", "unknown")
            raise RuntimeError(f"Cobalt error: {error_code}")

        download_url = data.get("url")
        if status == "picker":
            items = data.get("picker", [])
            if items:
                download_url = items[0].get("url")

        if not download_url:
            raise RuntimeError(f"Cobalt returned no URL (status={status})")

        filename = data.get("filename", "cobalt_download")
        ext = Path(filename).suffix or (".mp3" if match.media_type == MediaType.AUDIO else ".mp4")
        file_path = self._unique_path(ext)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                download_url, timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Cobalt download failed: HTTP {resp.status}")
                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)

        file_size = os.path.getsize(file_path)
        title = Path(filename).stem or "Download"

        return DownloadResult(
            file_path=file_path,
            title=title,
            duration=None,
            file_size=file_size,
            media_type=match.media_type,
            platform=match.platform,
        )

    # --- yt-dlp ---

    async def _run_ytdlp(
        self, match: PlatformMatch, quality: str, progress_cb=None,
    ) -> DownloadResult:
        ext = ".mp3" if match.media_type == MediaType.AUDIO else ".mp4"
        out_path = self._unique_path(ext)
        # yt-dlp needs template without extension for merge
        out_template = out_path.rsplit(".", 1)[0] + ".%(ext)s"

        args = self._build_ytdlp_args(match.url, match.media_type, quality)
        args.extend(["-o", out_template])

        log.info("Running yt-dlp for %s (quality=%s)", match.url, quality)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async for line in proc.stdout:
            text = line.decode(errors="replace").strip()
            if progress_cb and "[download]" in text:
                await progress_cb(text)

        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp exited with code {proc.returncode}")

        # Find the actual output file (extension may differ from template)
        base = out_path.rsplit(".", 1)[0]
        file_path = self._find_file_by_prefix(base)

        title = await self._get_title(match.url)
        file_size = os.path.getsize(file_path)

        return DownloadResult(
            file_path=file_path,
            title=title,
            duration=None,
            file_size=file_size,
            media_type=match.media_type,
            platform=match.platform,
        )

    # --- Music search (Spotify/Deezer) ---

    async def _run_music_search(
        self, match: PlatformMatch, progress_cb=None,
    ) -> DownloadResult:
        """Get track title from Spotify/Deezer, search YouTube, download audio."""
        title = None

        if match.platform == Platform.DEEZER:
            title = await self._get_deezer_title(match.url)
        elif match.platform == Platform.SPOTIFY:
            title = await self._get_spotify_title(match.url)
        else:
            title = await self._get_title(match.url)

        if not title or title == "Unknown":
            raise RuntimeError(f"Could not get track title from {match.platform.value}")

        log.info("%s track: '%s', searching YouTube", match.platform.value, title)
        search_match = PlatformMatch(
            platform=match.platform,
            media_type=MediaType.AUDIO,
            tool=DownloadTool.YTDLP,
            url=f"ytsearch:{title}",
        )
        return await self._run_ytdlp(search_match, "auto", progress_cb)

    async def _get_deezer_title(self, url: str) -> str | None:
        import re
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    page_html = await resp.text()
                    m = re.search(r"<title>(.+?)(?:\s*\|\s*Deezer)?</title>", page_html)
                    if m:
                        title = html.unescape(m.group(1).strip())
                        title = re.sub(
                            r"\s*[-\u2013]\s*(?:listen|Listen|Deezer|слухати|escuchar).*",
                            "", title, flags=re.IGNORECASE,
                        )
                        if title and len(title) > 2:
                            return title
        except Exception as e:
            log.warning("Failed to get Deezer title: %s", e)
        return None

    async def _get_spotify_title(self, url: str) -> str | None:
        """Get track title via Spotify oEmbed API (no auth needed)."""
        try:
            oembed_url = f"https://open.spotify.com/oembed?url={url}"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    oembed_url, timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    title = data.get("title", "")
                    author = data.get("author_name", "")
                    if title and author:
                        return f"{author} - {title}"
                    return title or None
        except Exception as e:
            log.warning("Failed to get Spotify title: %s", e)
        return None

    # --- gallery-dl ---

    async def _run_gallery_dl(
        self, match: PlatformMatch, progress_cb=None,
    ) -> DownloadResult:
        args = self._build_gallery_dl_args(match.url)
        log.info("Running gallery-dl for %s", match.url)

        # Use unique subdir to avoid conflicts
        dl_dir = os.path.join(self._cfg.download_dir, uuid.uuid4().hex[:8])
        os.makedirs(dl_dir, exist_ok=True)
        args[args.index("--dest") + 1] = dl_dir

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for line in proc.stdout:
            text = line.decode(errors="replace").strip()
            if progress_cb:
                await progress_cb(text)

        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"gallery-dl exited with code {proc.returncode}")

        # Find file in the subdirectory
        for root, _dirs, files in os.walk(dl_dir):
            for f in files:
                file_path = os.path.join(root, f)
                file_size = os.path.getsize(file_path)
                return DownloadResult(
                    file_path=file_path,
                    title=Path(f).stem,
                    duration=None,
                    file_size=file_size,
                    media_type=match.media_type,
                    platform=match.platform,
                )

        raise FileNotFoundError("gallery-dl produced no files")

    # --- Arg builders ---

    def _build_ytdlp_args(
        self, url: str, media_type: MediaType, quality: str,
    ) -> list[str]:
        args = ["yt-dlp", "--no-playlist", "--no-warnings", "--progress"]

        if self._cfg.cookies_file and os.path.exists(self._cfg.cookies_file):
            args.extend(["--cookies", self._cfg.cookies_file])

        if media_type == MediaType.AUDIO:
            args.extend([
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", f"{self._cfg.audio_bitrate}K",
                "--embed-thumbnail",
                "--add-metadata",
            ])
        else:
            height = {
                "auto": "1080", "1080": "1080", "720": "720", "480": "480",
            }.get(quality, "1080")
            args.extend([
                "-f",
                f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
                "--merge-output-format", "mp4",
            ])

        args.append(url)
        return args

    def _build_gallery_dl_args(self, url: str) -> list[str]:
        args = [
            "gallery-dl",
            "--dest", self._cfg.download_dir,
            "--no-mtime",
        ]
        if self._cfg.cookies_file and os.path.exists(self._cfg.cookies_file):
            args.extend(["--cookies", self._cfg.cookies_file])
        args.append(url)
        return args

    # --- Helpers ---

    async def _get_title(self, url: str) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp", "--print", "title", "--no-playlist", "--no-warnings", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            return stdout.decode().strip() or "Unknown"
        except Exception:
            return "Unknown"

    def _find_file_by_prefix(self, prefix: str) -> str:
        """Find a file that starts with the given prefix (any extension)."""
        import glob as glob_mod
        pattern = prefix + ".*"
        files = glob_mod.glob(pattern)
        if not files:
            # Fallback: check if exact path exists
            if os.path.exists(prefix):
                return prefix
            raise FileNotFoundError(f"No file matching {pattern}")
        return files[0]
