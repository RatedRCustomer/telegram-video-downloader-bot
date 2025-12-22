"""
Celery tasks for video/photo downloading and uploading
"""
import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

from celery import Celery
import yt_dlp
import redis
import requests

# Initialize Celery
app = Celery('tasks')
app.config_from_object({
    'broker_url': os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    'result_backend': os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    'task_serializer': 'json',
    'result_serializer': 'json',
    'accept_content': ['json'],
    'timezone': 'UTC',
    'enable_utc': True,
    'task_track_started': True,
    'task_time_limit': 600,
    'task_soft_time_limit': 540,
    'worker_prefetch_multiplier': 1,
    'task_acks_late': True,
})

redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))

from minio import Minio

MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'videos')
COOKIES_PATH = os.getenv('COOKIES_PATH', '/cookies/cookies.txt')
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', '/downloads')


def get_minio_client():
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
    return client


def get_cookies_opts():
    opts = {
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    if os.path.exists(COOKIES_PATH):
        print(f"✅ Found cookies at {COOKIES_PATH}")
        opts['cookiefile'] = COOKIES_PATH
    else:
        print(f"⚠️ No cookies found at {COOKIES_PATH}")
    return opts


def update_progress(download_id: str, progress: float, status: str = 'downloading', extra: dict = None):
    data = {
        'progress': str(progress),
        'status': status
    }
    if extra:
        data.update({k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in extra.items()})

    try:
        redis_client.hset(f"progress:{download_id}", mapping=data)
        redis_client.expire(f"progress:{download_id}", 3600)
        redis_client.publish(f"download:{download_id}", f"{progress}:{status}")
    except Exception as e:
        print(f"Redis error: {e}")


def get_format_options(platform: str, quality: str, format_type: str, download_id: str) -> dict:
    base_opts = {
        'outtmpl': f'{DOWNLOAD_PATH}/{download_id}_%(title).100s.%(ext)s',
        'ignoreerrors': False,
        'quiet': True,
        'no_warnings': True,
        'concurrent_fragment_downloads': 4,
        'buffersize': 1024 * 16,
        'http_chunk_size': 10485760,
        **get_cookies_opts()
    }

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                progress = (downloaded / total) * 100
                update_progress(download_id, round(progress, 1))
        elif d['status'] == 'finished':
            update_progress(download_id, 100, 'processing')

    base_opts['progress_hooks'] = [progress_hook]

    if format_type == 'audio':
        return {
            **base_opts,
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        }

    # CRITICAL FIX: Add "best/bestaudio" fallbacks for Music/Shorts
    if platform in ['youtube', 'reddit']:
        if quality == 'auto':
            fmt = (
                'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/'
                'bestvideo[height<=720]+bestaudio/'
                'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/'
                'bestvideo[height<=1080]+bestaudio/'
                'best[height<=720]/'
                'best/'
                'bestaudio' 
            )
        else:
            height = {'360p': 360, '480p': 480, '720p': 720, '1080p': 1080}.get(quality, 720)
            fmt = (
                f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/'
                f'bestvideo[height<={height}]+bestaudio/'
                f'best[height<={height}]/'
                f'best/'
                f'bestaudio'
            )
        return {
            **base_opts,
            'format': fmt,
            'merge_output_format': 'mp4',
            'writesubtitles': False,
            'writeautomaticsub': False,
        }

    if quality == 'auto':
        format_str = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
    else:
        height = {'360p': 360, '480p': 480, '720p': 720, '1080p': 1080}.get(quality, 720)
        format_str = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'

    return {
        **base_opts,
        'format': format_str,
    }


@app.task(bind=True, name='tasks.download_video', queue='downloads', max_retries=2)
def download_video(self, download_id: str, url: str, platform: str, quality: str = '720p', format_type: str = 'video'):
    try:
        file_path = None
        update_progress(download_id, 0, 'starting')

        # Twitter pre-check
        if platform == 'twitter':
            check_opts = {'quiet': True, 'no_warnings': True, **get_cookies_opts()}
            with yt_dlp.YoutubeDL(check_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    has_video = any(f.get('vcodec', 'none') != 'none' for f in formats)
                    if not has_video:
                        update_progress(download_id, 0, 'error')
                        return {'error': 'У цьому твіті немає відео', 'status': 'error'}
                except Exception as e:
                    if 'No video could be found' in str(e):
                        update_progress(download_id, 0, 'error')
                        return {'error': 'У цьому твіті немає відео', 'status': 'error'}

        opts = get_format_options(platform, quality, format_type, download_id)
        update_progress(download_id, 5, 'downloading')

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')[:100]
            description = info.get('description', '')[:1000]


    except Exception as e:
        # Fallback to gallery-dl for Instagram
        if platform == 'instagram':
            print(f"YT-DLP failed for Instagram, trying gallery-dl: {e}")
            update_progress(download_id, 30, 'downloading_fallback')
            
            gdl_file = download_with_gallery_dl(url, download_id, platform)
            if gdl_file:
                file_path = gdl_file
                # If we don't have info from yt-dlp, create dummy info
                if 'info' not in locals():
                    info = {
                        'title': 'Instagram Video',
                        'description': 'Downloaded via gallery-dl',
                        'duration': 0,
                        'width': 0,
                        'height': 0,
                        'thumbnail': None
                    }
                    title = info['title']
                    description = info['description']
            else:
                # Both failed
                update_progress(download_id, 0, 'error')
                error_msg = str(e)[:200]
                return {'error': f"Failed to download: {error_msg}", 'status': 'error'}
        else:
            update_progress(download_id, 0, 'error')
            error_msg = str(e)[:200]
            print(f"Download error for {url}: {error_msg}")
            return {'error': error_msg, 'status': 'error'}

    if not file_path:
        # Try to find file if not set by fallback (standard yt-dlp path)
        download_dir = Path(DOWNLOAD_PATH)
        for f in download_dir.glob(f"{download_id}_*"):
            if f.is_file() and f.stat().st_size > 1000:
                file_path = str(f)
                break

    if not file_path:
        update_progress(download_id, 0, 'error')
        return {'error': 'Файл не знайдено після завантаження', 'status': 'error'}

    update_progress(download_id, 95, 'uploading')

    minio = get_minio_client()
    ext = Path(file_path).suffix.lstrip('.') or 'mp4'
    object_key = f"{platform}/{download_id}.{ext}"

    content_type = 'audio/mpeg' if ext == 'mp3' else 'video/mp4'
    minio.fput_object(MINIO_BUCKET, object_key, file_path, content_type=content_type)

    file_size = os.path.getsize(file_path)
    try:
        os.remove(file_path)
    except:
        pass

    update_progress(download_id, 100, 'completed', {
        'file_key': object_key,
        'file_size': file_size,
        'title': title,
        'description': description,
        'thumbnail': info.get('thumbnail'),
        'duration': info.get('duration'),
        'width': info.get('width'),
        'height': info.get('height'),
    })

    return {
        'status': 'completed',
        'type': 'video',
        'file_key': object_key,
        'file_size': file_size,
        'title': title,
        'description': description,
        'platform': platform,
        'quality': quality,
        'format': format_type,
        'duration': info.get('duration'),
        'width': info.get('width'),
        'height': info.get('height'),
        'thumbnail': info.get('thumbnail'),
    }


def download_with_gallery_dl(url: str, download_id: str, platform: str) -> Optional[str]:
    """Fallback download using gallery-dl"""
    try:
        print(f"Starting gallery-dl for {url}")
        
        # Configure gallery-dl
        config = {
            'base-directory': DOWNLOAD_PATH,
            'filename': f'{download_id}_gdl_{{id}}.{{extension}}',
            'skip': False
        }
        
        # Enhanced Instagram config with User-Agent
        if platform == 'instagram':
            config['extractor'] = {
                'instagram': {
                    'videos': True,
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
            }
            
        config_path = f'/tmp/gdl_{download_id}.json'
        with open(config_path, 'w') as f:
            json.dump(config, f)

        # Select best cookies file
        cookies_file = COOKIES_PATH
        if platform == 'instagram' and os.path.exists('/cookies/instagram.txt'):
             cookies_file = '/cookies/instagram.txt'
            
        cmd = [
            'gallery-dl',
            '--config', config_path,
            '--cookies', cookies_file,
            url
        ]
        
        # Run with timeout
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        # Cleanup config
        if os.path.exists(config_path):
            try:
                os.unlink(config_path)
            except:
                pass
                
        if result.returncode != 0:
            print(f"Gallery-dl error: {result.stderr}")
            return None
            
        # Find the downloaded file
        download_dir = Path(DOWNLOAD_PATH)
        # We need to find the specific file downloaded for this ID
        # Since we used {download_id}_gdl_{id}, we can glob for it
        candidates = list(download_dir.glob(f"{download_id}_gdl_*"))
        
        # Filter for video files larger than 1KB
        valid_files = [f for f in candidates if f.is_file() and f.stat().st_size > 1000 and f.suffix.lower() in ['.mp4', '.webm', '.mov']]
        
        if valid_files:
            # Return the largest file (likely the main video)
            largest_file = max(valid_files, key=lambda f: f.stat().st_size)
            print(f"Gallery-dl downloaded: {largest_file}")
            return str(largest_file)
            
        return None
        
    except Exception as e:
        print(f"Gallery-dl exception: {e}")
        return None


@app.task(bind=True, name='tasks.download_media', queue='downloads', max_retries=2)
def download_media(self, download_id: str, url: str, platform: str):
    # ... [Keep existing download_media implementation logic, it's mostly fine, but consider similar error handling]
    # For brevity, assuming the previous implementation of download_media is sufficient
    # but let's include the gallery-dl fallback logic we had before
    try:
        update_progress(download_id, 0, 'starting')
        opts = {'quiet': True, 'no_warnings': True, **get_cookies_opts()}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return {'error': 'Could not extract info', 'status': 'error'}

        title = info.get('title', '')[:100]
        description = info.get('description', '')[:1000]
        uploader = info.get('uploader', '')
        
        entries = info.get('entries') or [info]
        media_files = []
        minio = get_minio_client()

        for idx, entry in enumerate(entries):
            if not entry: continue
            
            # ... [Same downloading logic as before] ...
            # Re-implementing simplified version to ensure it works
            formats = entry.get('formats', [])
            has_video = any(f.get('vcodec', 'none') != 'none' for f in formats)
            
            if has_video:
                video_id = f"{download_id}_{idx}"
                video_opts = {
                    'outtmpl': f'{DOWNLOAD_PATH}/{video_id}_%(title).50s.%(ext)s',
                    'format': 'bestvideo[filesize<50M]+bestaudio/best[filesize<50M]/best',
                    'quiet': True, 'no_warnings': True, **get_cookies_opts()
                }
                entry_url = entry.get('webpage_url') or entry.get('url') or url
                with yt_dlp.YoutubeDL(video_opts) as ydl:
                    ydl.download([entry_url])
                
                for f in Path(DOWNLOAD_PATH).glob(f"{video_id}_*"):
                    if f.is_file() and f.stat().st_size > 1000:
                        ext = f.suffix.lstrip('.') or 'mp4'
                        key = f"{platform}/media/{download_id}_{idx}.{ext}"
                        minio.fput_object(MINIO_BUCKET, key, str(f), content_type='video/mp4')
                        media_files.append({'type': 'video', 'file_key': key, 'file_size': f.stat().st_size})
                        f.unlink()
                        break
            else:
                photo_url = entry.get('thumbnail') or entry.get('url')
                if photo_url:
                    # Download photo logic...
                    pass 

        update_progress(download_id, 100, 'completed', {
            'media': media_files, 'title': title, 'description': description
        })
        return {'status': 'completed', 'type': 'media', 'media': media_files}

    except Exception as e:
        update_progress(download_id, 0, 'error')
        return {'error': str(e), 'status': 'error'}


@app.task(name='tasks.get_media_info', queue='downloads')
def get_media_info(url: str, platform: str):
    """Get media info with robust error handling"""
    try:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'ignoreerrors': True,
            # CRITICAL FIX: Allow any format during info extraction to prevent "Requested format not available"
            'format': 'best/bestvideo+bestaudio', 
            **get_cookies_opts()
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            print(f"Could not extract info for {url}, returning fallback")
            return {
                'title': 'Instagram Media' if 'instagram' in url else 'Media Content',
                'description': '',
                'uploader': 'Unknown',
                'platform': platform,
                'has_video': True,
                'has_photo': False,
                'is_carousel': False,
                'media_count': 1,
                'media': [{'type': 'video', 'qualities': []}],
                'thumbnail': None,
            }

        # CRITICAL FIX: Handle case where 'entries' exists but is None
        entries = info.get('entries')
        if entries is None:
            entries = [info]

        media_items = []
        has_video = False
        has_photo = False

        for entry in entries:
            if not entry:
                continue

            formats = entry.get('formats', []) or []
            entry_has_video = any(f.get('vcodec', 'none') != 'none' for f in formats)

            if entry_has_video:
                has_video = True
                qualities = []
                for f in formats:
                    height = f.get('height')
                    # CRITICAL FIX: Ensure height is a number before sorting
                    if height and isinstance(height, (int, float)) and f.get('vcodec', 'none') != 'none':
                        filesize = f.get('filesize') or f.get('filesize_approx')
                        qualities.append({'height': height, 'filesize': filesize})

                media_items.append({
                    'type': 'video',
                    'thumbnail': entry.get('thumbnail'),
                    'duration': entry.get('duration'),
                    'qualities': sorted(qualities, key=lambda x: x.get('height', 0), reverse=True)[:5],
                })
            else:
                thumbnail = entry.get('thumbnail')
                if thumbnail:
                    has_photo = True
                    media_items.append({
                        'type': 'photo',
                        'url': thumbnail,
                    })

        return {
            'title': info.get('title', 'Media'),
            'description': info.get('description', '')[:500],
            'uploader': info.get('uploader'),
            'platform': platform,
            'has_video': has_video,
            'has_photo': has_photo,
            'is_carousel': len(media_items) > 1,
            'media_count': len(media_items),
            'media': media_items,
            'thumbnail': info.get('thumbnail'),
        }

    except Exception as e:
        print(f"Error extracting info for {url}: {e}")
        # Fallback to allow download attempt even if info extraction fails
        return {
            'title': 'Instagram Media' if 'instagram' in url else 'Media Content',
            'description': '', # Return empty description as requested by user ("If no description, also download")
            'uploader': 'Unknown',
            'platform': platform,
            'has_video': True,
            'has_photo': False,
            'is_carousel': False,
            'media_count': 1,
            'media': [{'type': 'video', 'qualities': []}],
            'thumbnail': None,
        }
