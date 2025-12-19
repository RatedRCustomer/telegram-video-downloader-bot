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


def update_progress(download_id: str, progress: float, status: str = 'downloading', extra: dict = None):
    """Update progress in Redis"""
    data = {
        'progress': str(progress),
        'status': status
    }
    if extra:
        data.update({k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in extra.items()})

    redis_client.hset(f"progress:{download_id}", mapping=data)
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
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        }

    # Platform-specific options for YouTube/Reddit
    if platform in ['youtube', 'reddit']:
        # More flexible format selection for YouTube
        # Try best formats first, then fall back to combined formats
        if quality == 'auto':
            # Prefer formats under 50MB, fallback to 720p, then best available
            fmt = (
                'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/'
                'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/'
                'best[height<=720]/best'
            )
        else:
            height = {'360p': 360, '480p': 480, '720p': 720, '1080p': 1080}.get(quality, 720)
            fmt = (
                f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/'
                f'bestvideo[height<={height}]+bestaudio/'
                f'best[height<={height}]/best'
            )
        return {
            **base_opts,
            'format': fmt,
            'merge_output_format': 'mp4',
            'writesubtitles': False,  # Disable subtitles for now to avoid issues
            'writeautomaticsub': False,
        }

    # Generic format for other platforms
    if quality == 'auto':
        format_str = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
    else:
        height = {'360p': 360, '480p': 480, '720p': 720, '1080p': 1080}.get(quality, 720)
        format_str = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'

    return {
        **base_opts,
        'format': format_str,
    }


def extract_media_info(url: str, platform: str) -> Dict[str, Any]:
    """
    Extract media info from URL using yt-dlp.
    Returns info about videos, photos, and captions.
    """
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

    # Determine content type
    entries = info.get('entries', [info])
    if not entries:
        entries = [info]

    result = {
        'title': info.get('title', ''),
        'description': info.get('description', ''),
        'uploader': info.get('uploader', ''),
        'platform': platform,
        'url': url,
        'media': [],
        'has_video': False,
        'has_photo': False,
        'is_carousel': False,
    }

    for entry in entries:
        if not entry:
            continue

        formats = entry.get('formats', [])

        # Check for video
        has_video = any(f.get('vcodec', 'none') != 'none' for f in formats)

        if has_video:
            result['has_video'] = True
            result['media'].append({
                'type': 'video',
                'url': entry.get('webpage_url') or entry.get('url'),
                'thumbnail': entry.get('thumbnail'),
                'duration': entry.get('duration'),
                'width': entry.get('width'),
                'height': entry.get('height'),
            })
        else:
            # Check for images
            thumbnail = entry.get('thumbnail')
            if thumbnail and platform in ['instagram', 'twitter', 'threads', 'facebook']:
                result['has_photo'] = True
                result['media'].append({
                    'type': 'photo',
                    'url': thumbnail,
                })

    # Check for Instagram/Twitter image posts specifically
    if platform == 'instagram' and not result['has_video']:
        # Try to get images from thumbnails or other sources
        thumbnails = info.get('thumbnails', [])
        if thumbnails:
            result['has_photo'] = True
            for thumb in thumbnails:
                if thumb.get('url'):
                    result['media'].append({
                        'type': 'photo',
                        'url': thumb['url'],
                    })

    result['is_carousel'] = len(result['media']) > 1

    return result


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
            description = info.get('description', '')[:1000]

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

    except Exception as e:
        update_progress(download_id, 0, 'error')
        error_msg = str(e)[:200]
        print(f"Download error for {url}: {error_msg}")

        # Retry for network errors
        if 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
            raise self.retry(countdown=10, exc=e)

        return {'error': error_msg, 'status': 'error'}


@app.task(bind=True, name='tasks.download_media', queue='downloads', max_retries=2)
def download_media(self, download_id: str, url: str, platform: str):
    """
    Download media (photos/videos) from URL.
    Handles carousels, single photos, and videos with captions.
    Returns: dict with media files info
    """
    try:
        update_progress(download_id, 0, 'starting')

        # Extract info first
        opts = {
            'quiet': True,
            'no_warnings': True,
            **get_cookies_opts()
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            update_progress(download_id, 0, 'error')
            return {'error': 'Не вдалося отримати інформацію', 'status': 'error'}

        title = info.get('title', '')[:100]
        description = info.get('description', '')[:1000]
        uploader = info.get('uploader', '')

        # Check what type of content we have
        entries = info.get('entries', [info])
        if not entries:
            entries = [info]

        media_files = []
        minio = get_minio_client()

        total_items = len(entries)

        for idx, entry in enumerate(entries):
            if not entry:
                continue

            progress = ((idx + 1) / total_items) * 80
            update_progress(download_id, round(progress), 'downloading')

            formats = entry.get('formats', [])
            has_video = any(f.get('vcodec', 'none') != 'none' for f in formats)

            if has_video:
                # Download video
                video_id = f"{download_id}_{idx}"
                video_opts = {
                    'outtmpl': f'{DOWNLOAD_PATH}/{video_id}_%(title).50s.%(ext)s',
                    'format': 'bestvideo[filesize<50M]+bestaudio/best[filesize<50M]/best',
                    'quiet': True,
                    'no_warnings': True,
                    **get_cookies_opts()
                }

                entry_url = entry.get('webpage_url') or entry.get('url') or url
                with yt_dlp.YoutubeDL(video_opts) as ydl:
                    ydl.download([entry_url])

                # Find downloaded file
                for f in Path(DOWNLOAD_PATH).glob(f"{video_id}_*"):
                    if f.is_file() and f.stat().st_size > 1000:
                        ext = f.suffix.lstrip('.') or 'mp4'
                        object_key = f"{platform}/media/{download_id}_{idx}.{ext}"
                        minio.fput_object(MINIO_BUCKET, object_key, str(f), content_type='video/mp4')
                        media_files.append({
                            'type': 'video',
                            'file_key': object_key,
                            'file_size': f.stat().st_size,
                            'duration': entry.get('duration'),
                            'width': entry.get('width'),
                            'height': entry.get('height'),
                        })
                        f.unlink()
                        break
            else:
                # Try to download photo
                photo_url = entry.get('thumbnail') or entry.get('url')
                if photo_url:
                    try:
                        response = requests.get(photo_url, timeout=30, stream=True)
                        if response.status_code == 200:
                            # Determine extension
                            content_type = response.headers.get('content-type', 'image/jpeg')
                            if 'png' in content_type:
                                ext = 'png'
                            elif 'gif' in content_type:
                                ext = 'gif'
                            elif 'webp' in content_type:
                                ext = 'webp'
                            else:
                                ext = 'jpg'

                            # Save locally then upload
                            local_path = f"{DOWNLOAD_PATH}/{download_id}_{idx}.{ext}"
                            with open(local_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)

                            object_key = f"{platform}/media/{download_id}_{idx}.{ext}"
                            minio.fput_object(MINIO_BUCKET, object_key, local_path, content_type=content_type)

                            file_size = os.path.getsize(local_path)
                            os.remove(local_path)

                            media_files.append({
                                'type': 'photo',
                                'file_key': object_key,
                                'file_size': file_size,
                            })
                    except Exception as e:
                        print(f"Error downloading photo: {e}")

        # If no media found via yt-dlp, try gallery-dl for Instagram
        if not media_files and platform == 'instagram':
            media_files = download_with_gallery_dl(download_id, url, minio)

        if not media_files:
            update_progress(download_id, 0, 'error')
            return {'error': 'Медіа не знайдено', 'status': 'error'}

        update_progress(download_id, 100, 'completed', {
            'media': media_files,
            'title': title,
            'description': description,
            'uploader': uploader,
            'is_carousel': len(media_files) > 1,
        })

        return {
            'status': 'completed',
            'type': 'media',
            'media': media_files,
            'title': title,
            'description': description,
            'uploader': uploader,
            'platform': platform,
            'is_carousel': len(media_files) > 1,
        }

    except Exception as e:
        update_progress(download_id, 0, 'error')
        error_msg = str(e)[:200]
        print(f"Media download error for {url}: {error_msg}")

        if 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
            raise self.retry(countdown=10, exc=e)

        return {'error': error_msg, 'status': 'error'}


def download_with_gallery_dl(download_id: str, url: str, minio) -> List[Dict]:
    """
    Download media using gallery-dl (better for Instagram photos).
    Returns list of media file info dicts.
    """
    media_files = []
    temp_dir = f"{DOWNLOAD_PATH}/gallery_{download_id}"

    try:
        os.makedirs(temp_dir, exist_ok=True)

        # Build gallery-dl command
        cmd = [
            'gallery-dl',
            '--dest', temp_dir,
            '--filename', f'{download_id}_{{num}}.{{extension}}',
            '--no-mtime',
            '-q',
        ]

        # Add cookies if available
        if os.path.exists(COOKIES_PATH):
            cmd.extend(['--cookies', COOKIES_PATH])

        cmd.append(url)

        # Run gallery-dl
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            print(f"gallery-dl error: {result.stderr}")
            return []

        # Find downloaded files
        for f in Path(temp_dir).rglob('*'):
            if f.is_file() and f.stat().st_size > 1000:
                ext = f.suffix.lstrip('.').lower()

                # Determine type
                if ext in ['mp4', 'webm', 'mov', 'avi']:
                    media_type = 'video'
                    content_type = 'video/mp4'
                elif ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                    media_type = 'photo'
                    content_type = f'image/{ext}' if ext != 'jpg' else 'image/jpeg'
                else:
                    continue

                # Upload to MinIO
                object_key = f"instagram/media/{f.name}"
                minio.fput_object(MINIO_BUCKET, object_key, str(f), content_type=content_type)

                media_files.append({
                    'type': media_type,
                    'file_key': object_key,
                    'file_size': f.stat().st_size,
                })

    except subprocess.TimeoutExpired:
        print("gallery-dl timeout")
    except Exception as e:
        print(f"gallery-dl error: {e}")
    finally:
        # Cleanup
        import shutil
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

    return media_files


@app.task(name='tasks.get_media_info', queue='downloads')
def get_media_info(url: str, platform: str):
    """
    Get media info without downloading.
    Returns info about what type of content is available.
    """
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

        entries = info.get('entries', [info])
        if not entries:
            entries = [info]

        media_items = []
        has_video = False
        has_photo = False

        for entry in entries:
            if not entry:
                continue

            formats = entry.get('formats', [])
            entry_has_video = any(f.get('vcodec', 'none') != 'none' for f in formats)

            if entry_has_video:
                has_video = True
                qualities = []
                for f in formats:
                    height = f.get('height')
                    if height and f.get('vcodec', 'none') != 'none':
                        filesize = f.get('filesize') or f.get('filesize_approx')
                        qualities.append({'height': height, 'filesize': filesize})

                media_items.append({
                    'type': 'video',
                    'thumbnail': entry.get('thumbnail'),
                    'duration': entry.get('duration'),
                    'qualities': sorted(qualities, key=lambda x: x['height'], reverse=True)[:5],
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
        return {'error': str(e)[:100]}


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
            'description': info.get('description', '')[:500],
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
