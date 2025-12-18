"""
Celery tasks for video downloading and uploading
"""
import os
import uuid
import tempfile
from pathlib import Path
from datetime import datetime

from celery import Celery
import yt_dlp
import redis

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
    'task_time_limit': 600,  # 10 minutes max
    'task_soft_time_limit': 540,  # 9 minutes soft limit
    'worker_prefetch_multiplier': 1,
    'task_acks_late': True,
})

# Redis for progress updates
redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))

# MinIO client
from minio import Minio

MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'videos')
COOKIES_PATH = os.getenv('COOKIES_PATH', '/cookies/cookies.txt')
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', '/downloads')


def get_minio_client():
    """Get MinIO client"""
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    # Ensure bucket exists
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
    return client


def get_cookies_opts():
    """Get cookies options if file exists"""
    if os.path.exists(COOKIES_PATH):
        return {'cookiefile': COOKIES_PATH}
    return {}


def update_progress(download_id: str, progress: float, status: str = 'downloading'):
    """Update progress in Redis"""
    redis_client.hset(f"progress:{download_id}", mapping={
        'progress': str(progress),
        'status': status
    })
    redis_client.expire(f"progress:{download_id}", 3600)
    # Publish for real-time updates
    redis_client.publish(f"download:{download_id}", f"{progress}:{status}")


def get_format_options(platform: str, quality: str, format_type: str, download_id: str) -> dict:
    """Get yt-dlp options for platform"""
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

    # Progress hook
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

    # Audio only
    if format_type == 'audio':
        return {
            **base_opts,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        }

    # Auto quality
    if quality == 'auto':
        format_str = 'bestvideo[filesize<50M]+bestaudio/best[filesize<50M]/bestvideo[height<=720]+bestaudio/best[height<=720]/best'
    else:
        height = {'360p': 360, '480p': 480, '720p': 720, '1080p': 1080}.get(quality, 720)
        format_str = f'best[height<={height}]/best'

    # Platform-specific options
    if platform in ['youtube', 'reddit']:
        if quality == 'auto':
            fmt = 'bestvideo[filesize<50M]+bestaudio/best[filesize<50M]/bestvideo[height<=720]+bestaudio/best'
        else:
            height = {'360p': 360, '480p': 480, '720p': 720, '1080p': 1080}.get(quality, 720)
            fmt = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'
        return {
            **base_opts,
            'format': fmt,
            'merge_output_format': 'mp4',
            'writesubtitles': platform == 'youtube',
            'writeautomaticsub': platform == 'youtube',
            'subtitleslangs': ['uk', 'en', 'ru'] if platform == 'youtube' else [],
        }

    return {
        **base_opts,
        'format': format_str,
    }


@app.task(bind=True, name='tasks.download_video', queue='downloads', max_retries=2)
def download_video(self, download_id: str, url: str, platform: str, quality: str = '720p', format_type: str = 'video'):
    """
    Download video task
    Returns: dict with file info or error
    """
    try:
        update_progress(download_id, 0, 'starting')

        # Check if Twitter has video
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

        # Get options and download
        opts = get_format_options(platform, quality, format_type, download_id)

        update_progress(download_id, 5, 'downloading')

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')[:100]

        # Find downloaded file
        download_dir = Path(DOWNLOAD_PATH)
        file_path = None
        for f in download_dir.glob(f"{download_id}_*"):
            if f.is_file() and f.stat().st_size > 1000:
                file_path = str(f)
                break

        if not file_path:
            update_progress(download_id, 0, 'error')
            return {'error': 'Файл не знайдено після завантаження', 'status': 'error'}

        update_progress(download_id, 95, 'uploading')

        # Upload to MinIO
        minio = get_minio_client()
        ext = Path(file_path).suffix.lstrip('.') or 'mp4'
        object_key = f"{platform}/{download_id}.{ext}"

        content_type = 'audio/mpeg' if ext == 'mp3' else 'video/mp4'
        minio.fput_object(MINIO_BUCKET, object_key, file_path, content_type=content_type)

        file_size = os.path.getsize(file_path)

        # Cleanup local file
        try:
            os.remove(file_path)
        except:
            pass

        update_progress(download_id, 100, 'completed')

        return {
            'status': 'completed',
            'file_key': object_key,
            'file_size': file_size,
            'title': title,
            'platform': platform,
            'quality': quality,
            'format': format_type,
            'duration': info.get('duration'),
            'width': info.get('width'),
            'height': info.get('height'),
            'thumbnail': info.get('thumbnail'),
        }

    except Exception as e:
        update_progress(download_id, 0, 'error')
        error_msg = str(e)[:200]
        print(f"Download error for {url}: {error_msg}")

        # Retry for network errors
        if 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
            raise self.retry(countdown=10, exc=e)

        return {'error': error_msg, 'status': 'error'}


@app.task(name='tasks.get_video_info', queue='downloads')
def get_video_info(url: str):
    """Get video info without downloading"""
    try:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            **get_cookies_opts()
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return {'error': 'Could not extract info'}

        # Get available qualities
        formats = info.get('formats', [])
        qualities = []
        for f in formats:
            height = f.get('height')
            if height and f.get('vcodec', 'none') != 'none':
                filesize = f.get('filesize') or f.get('filesize_approx')
                qualities.append({
                    'height': height,
                    'filesize': filesize,
                })

        return {
            'title': info.get('title', 'Video'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'uploader': info.get('uploader'),
            'view_count': info.get('view_count'),
            'qualities': sorted(qualities, key=lambda x: x['height'], reverse=True)[:5],
        }

    except Exception as e:
        return {'error': str(e)[:100]}


@app.task(name='tasks.cleanup_old_files', queue='downloads')
def cleanup_old_files():
    """Cleanup old files from MinIO"""
    from datetime import datetime, timedelta

    try:
        minio = get_minio_client()
        cutoff = datetime.utcnow() - timedelta(days=7)
        deleted = 0

        for obj in minio.list_objects(MINIO_BUCKET, recursive=True):
            if obj.last_modified.replace(tzinfo=None) < cutoff:
                minio.remove_object(MINIO_BUCKET, obj.object_name)
                deleted += 1

        return {'deleted': deleted}

    except Exception as e:
        return {'error': str(e)}
