from flask import Flask, request, jsonify, Response
import yt_dlp
import gallery_dl
import os
import threading
import time
import uuid
import subprocess
from pathlib import Path
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import queue
from collections import defaultdict
import json
import hashlib
import sqlite3
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import asyncio

async def async_cleanup():
    while True:
        await asyncio.sleep(3600)
        # cleanup logic

session = requests.Session()
retry = Retry(total=3, backoff_factor=0.3)
adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
session.mount('http://', adapter)
session.mount('https://', adapter)

# Prometheus metrics
downloads_total = Counter('downloads_total', 'Total downloads', ['platform', 'quality', 'format'])
downloads_success = Counter('downloads_success', 'Successful downloads', ['platform'])
downloads_failed = Counter('downloads_failed', 'Failed downloads', ['platform', 'reason'])
cache_hits = Counter('cache_hits_total', 'Cache hits', ['platform'])
cache_misses = Counter('cache_misses_total', 'Cache misses', ['platform'])
download_duration = Histogram('download_duration_seconds', 'Download duration', ['platform'])
active_downloads_gauge = Gauge('active_downloads', 'Currently active downloads')
queue_size_gauge = Gauge('queue_size', 'Download queue size')
cache_size_gauge = Gauge('cache_size_mb', 'Cache size in MB')

app = Flask(__name__)

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour", "10 per minute"]
)
limiter.init_app(app)

# Download queue
download_queue = queue.Queue(maxsize=5)
downloads = {}
download_stats = defaultdict(int)

# SQLite для кешування
DB_PATH = '/downloads/cache.db'

def init_cache_db():
    """Ініціалізація БД для кешування"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS video_cache
                 (url_hash TEXT PRIMARY KEY,
                  original_url TEXT,
                  file_path TEXT,
                  title TEXT,
                  platform TEXT,
                  quality TEXT,
                  format TEXT,
                  downloaded_at REAL,
                  file_size INTEGER,
                  access_count INTEGER DEFAULT 0,
                  last_accessed REAL)''')
    conn.commit()
    conn.close()

def get_url_hash(url, quality='720p', format='video'):
    """Генеруємо hash URL + параметрів"""
    key = f"{url}_{quality}_{format}"
    return hashlib.md5(key.encode()).hexdigest()

def check_cache(url, quality='720p', format='video'):
    """Перевіряємо чи є відео в кеші"""
    try:
        url_hash = get_url_hash(url, quality, format)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''SELECT file_path, title, platform, file_size 
                     FROM video_cache 
                     WHERE url_hash = ?''', (url_hash,))
        result = c.fetchone()
        
        if result:
            file_path, title, platform, file_size = result
            if Path(file_path).exists():
                # PROMETHEUS: Cache hit
                cache_hits.labels(platform=platform).inc()
                
                c.execute('''UPDATE video_cache 
                           SET access_count = access_count + 1,
                               last_accessed = ?
                           WHERE url_hash = ?''', (time.time(), url_hash))
                conn.commit()
                conn.close()
                
                return {
                    'cached': True,
                    'file_path': file_path,
                    'title': title,
                    'platform': platform,
                    'file_size': file_size
                }
            else:
                c.execute('DELETE FROM video_cache WHERE url_hash = ?', (url_hash,))
                conn.commit()
        
        # PROMETHEUS: Cache miss
        platform = detect_platform(url)
        cache_misses.labels(platform=platform).inc()
        
        conn.close()
        return {'cached': False}
        
    except Exception as e:
        print(f"Cache check error: {e}")
        return {'cached': False}

def save_to_cache(url, file_path, title, platform, quality='720p', format='video'):
    """Зберігаємо відео в кеш"""
    try:
        url_hash = get_url_hash(url, quality, format)
        file_size = Path(file_path).stat().st_size
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''INSERT OR REPLACE INTO video_cache 
                     (url_hash, original_url, file_path, title, platform, 
                      quality, format, downloaded_at, file_size, last_accessed)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (url_hash, url, file_path, title, platform, 
                   quality, format, time.time(), file_size, time.time()))
        
        conn.commit()
        conn.close()
        print(f"Saved to cache: {url}")
        
    except Exception as e:
        print(f"Cache save error: {e}")

class DownloadManager:
    def __init__(self, max_concurrent=2):
        self.max_concurrent = max_concurrent
        self.active_count = 0
        self.lock = threading.Lock()
        
    def can_start_download(self):
        with self.lock:
            return self.active_count < self.max_concurrent
    
    def start_download(self):
        with self.lock:
            if self.active_count < self.max_concurrent:
                self.active_count += 1
                return True
            return False
    
    def finish_download(self):
        with self.lock:
            self.active_count = max(0, self.active_count - 1)

download_manager = DownloadManager()

def get_platform_options(platform, download_id, quality='720p', format='video'):
    """Оптимізовані налаштування для кожної платформи"""
    
    base_opts = {
        'outtmpl': f'/downloads/{download_id}_%(title)s.%(ext)s',
        'ignoreerrors': False,
    }
    
    height_limit = {
        '360p': 360,
        '480p': 480,
        '720p': 720,
        '1080p': 1080
    }.get(quality, 720)
    
    # AUDIO-ONLY режим
    if format == 'audio':
        return {**base_opts,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        }
    
    # INSTAGRAM
    if platform == 'instagram':
        return {**base_opts,
            'format': f'best[height<={height_limit}]/best',
            'merge_output_format': 'mp4',
            'writesubtitles': True,
            'subtitleslangs': ['uk', 'en', 'ru'],
            'embedsubtitles': True,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }, {
                'key': 'FFmpegEmbedSubtitle',
            }],
            'postprocessor_args': {
                'videoconvertor': [
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-crf', '23',
                    '-profile:v', 'baseline',
                    '-level', '3.0',
                    '-pix_fmt', 'yuv420p',
                    '-bf', '0',
                    '-refs', '1',
                    '-g', '30',
                    '-sc_threshold', '0',
                    '-movflags', '+faststart',
                    '-maxrate', '2M',
                    '-bufsize', '4M',
                    '-c:a', 'aac',
                    '-strict', 'experimental',
                    '-ar', '44100',
                    '-ac', '2',
                    '-b:a', '128k',
                    '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2'
                ]
            }
        }
    
    # TIKTOK
    elif platform == 'tiktok':
        return {**base_opts,
            'format': f'best[height<={height_limit}]/best',
            'writesubtitles': True,
            'subtitleslangs': ['uk', 'en'],
            'embedsubtitles': True,
            'extractor_args': {
                'tiktok': {
                    'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'
                }
            }
        }
    
    # REDDIT
    elif platform == 'reddit':
        return {**base_opts,
            'format': f'best[height<={height_limit}]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'writesubtitles': True,
            'subtitleslangs': ['uk', 'en'],
            'embedsubtitles': True
        }
    
    # YOUTUBE
    elif platform == 'youtube':
        return {**base_opts,
            'format': f'best[height<={height_limit}]/bestvideo+bestaudio/best',
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['uk', 'en', 'ru'],
            'embedsubtitles': True,
            'merge_output_format': 'mp4'
        }
    
    # PINTEREST
    elif platform == 'pinterest':
        return {**base_opts,
            'format': f'best[height<={height_limit}]/bestvideo+bestaudio/best'
        }
    
    # DEFAULT
    else:
        return {**base_opts,
            'format': f'best[height<={height_limit}]/best',
            'writesubtitles': True,
            'subtitleslangs': ['uk', 'en'],
            'embedsubtitles': True
        }

def download_with_ytdlp(url, download_id, platform, quality='720p', format='video'):
    """Стандартне завантаження через yt-dlp"""
    try:
        ydl_opts = get_platform_options(platform, download_id, quality, format)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', f'{platform}_video_{download_id}')
            
            downloads[download_id]['title'] = title
            ydl.download([url])
            
            download_dir = Path('/downloads')
            for file_path in download_dir.glob(f"{download_id}_*"):
                if file_path.is_file() and file_path.stat().st_size > 1000:
                    downloads[download_id]['file_path'] = str(file_path)
                    downloads[download_id]['status'] = 'completed'
                    downloads[download_id]['format'] = format
                    
                    save_to_cache(url, str(file_path), title, platform, quality, format)
                    return True
                    
        return False
        
    except Exception as e:
        print(f"YT-DLP failed for {url}: {e}")
        return False

def download_with_gallery_dl(url, download_id, platform):
    """Backup завантаження через gallery-dl"""
    try:
        config = {
            'base-directory': '/downloads',
            'filename': f'{download_id}_{{title}}.{{extension}}',
            'skip': False
        }
        
        if platform == 'instagram':
            config['extractor'] = {'instagram': {'videos': True}}
        elif platform == 'tiktok':
            config['extractor'] = {'tiktok': {'api': 'mobile', 'format': 'best'}}
        elif platform == 'pinterest':
            config['extractor'] = {'pinterest': {'videos': True, 'images': True}}
        elif platform == 'reddit':
            config['extractor'] = {'reddit': {'videos': True, 'format': 'best'}}
        
        config_path = f'/tmp/gallery_dl_config_{download_id}.json'
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        cmd = ['gallery-dl', '--config', config_path, url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            download_dir = Path('/downloads')
            for file_path in download_dir.glob(f"{download_id}_*"):
                if file_path.is_file() and file_path.stat().st_size > 1000:
                    downloads[download_id]['file_path'] = str(file_path)
                    downloads[download_id]['status'] = 'completed'
                    downloads[download_id]['title'] = file_path.stem.replace(f'{download_id}_', '')
                    os.unlink(config_path)
                    return True
        
        if os.path.exists(config_path):
            os.unlink(config_path)
        return False
        
    except Exception as e:
        print(f"Gallery-dl failed for {url}: {e}")
        return False

def managed_download_worker(url, download_id, quality='720p', format='video'):
    """Керований worker з обмеженням ресурсів"""
    try:
        os.nice(10)
        download_worker(url, download_id, quality, format)
    finally:
        download_manager.finish_download()
        try:
            next_item = download_queue.get_nowait()
            next_id, next_url, next_quality, next_format = next_item
            if downloads[next_id]['status'] == 'queued':
                if download_manager.start_download():
                    thread = threading.Thread(target=managed_download_worker, 
                                            args=(next_url, next_id, next_quality, next_format))
                    thread.start()
        except queue.Empty:
            pass

def download_worker(url, download_id, quality='720p', format='video'):
    """Головна функція завантаження з fallback логікою"""
    try:
        downloads[download_id]['status'] = 'downloading'
        platform = downloads[download_id]['platform']
        
        print(f"Starting download from {platform}: {url} (quality={quality}, format={format})")
        
        success = download_with_ytdlp(url, download_id, platform, quality, format)
        
        if not success and format == 'video' and platform in ['tiktok', 'reddit', 'pinterest', 'instagram']:
            print(f"YT-DLP failed, trying gallery-dl for {platform}")
            success = download_with_gallery_dl(url, download_id, platform)
        
        if not success:
            downloads[download_id]['status'] = 'error'
            downloads[download_id]['error'] = f'Both yt-dlp and gallery-dl failed for {platform}'
            
    except Exception as e:
        downloads[download_id]['status'] = 'error'  
        downloads[download_id]['error'] = str(e)
        print(f"Error downloading {url}: {e}")

@app.route('/add', methods=['POST'])
@limiter.limit("5 per minute")
def download_video():
    data = request.json
    url = data.get('url')
    quality = data.get('quality', '720p')
    format = data.get('format', 'video')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    # ПЕРЕВІРЯЄМО КЕШ
    cache_result = check_cache(url, quality, format)
    if cache_result['cached']:
        print(f"✅ CACHE HIT for {url}")
        return jsonify({
            'status': 'completed',
            'url': url,
            'cached': True,
            'file_path': cache_result['file_path'],
            'title': cache_result['title'],
            'platform': cache_result['platform'],
            'format': format,
            'id': 'cached_' + get_url_hash(url, quality, format)
        }), 200
    
    print(f"❌ CACHE MISS for {url} - downloading...")
    
    if download_queue.full():
        return jsonify({
            'error': 'Server busy. Too many downloads in queue.',
            'queue_full': True
        }), 429
    
    download_id = str(uuid.uuid4())
    downloads[download_id] = {
        'status': 'queued',
        'url': url,
        'file_path': None,
        'error': None,
        'platform': detect_platform(url),
        'quality': quality,
        'format': format,
        'queued_at': time.time()
    }
    
    if download_manager.start_download():
        thread = threading.Thread(target=managed_download_worker, args=(url, download_id, quality, format))
        thread.start()
    else:
        try:
            download_queue.put((download_id, url, quality, format), timeout=1)
        except queue.Full:
            return jsonify({'error': 'Queue full'}), 429
    
    return jsonify({'status': 'queued', 'url': url, 'id': download_id}), 200

def detect_platform(url):
    url_lower = url.lower()
    if 'tiktok.com' in url_lower or 'vm.tiktok.com' in url_lower:
        return 'tiktok'
    elif 'instagram.com' in url_lower:
        return 'instagram' 
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
        return 'twitter'
    elif 'facebook.com' in url_lower or 'fb.watch' in url_lower:
        return 'facebook'
    elif 'reddit.com' in url_lower:
        return 'reddit'
    elif 'pinterest.com' in url_lower or 'pin.it' in url_lower:
        return 'pinterest'
    else:
        return 'unknown'

@app.route('/status/<download_id>', methods=['GET'])
def get_status(download_id):
    if download_id.startswith('cached_'):
        return jsonify({'status': 'completed', 'cached': True}), 200
    
    if download_id in downloads:
        return jsonify(downloads[download_id]), 200
    else:
        return jsonify({'error': 'Download not found'}), 404

@app.route('/cache/stats', methods=['GET'])
def cache_stats():
    """Статистика кешу"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*), SUM(file_size), SUM(access_count) FROM video_cache')
        result = c.fetchone()
        count = result[0] or 0
        total_size = result[1] or 0
        total_accesses = result[2] or 0
        
        c.execute('''SELECT platform, COUNT(*), SUM(file_size) 
                     FROM video_cache GROUP BY platform''')
        platform_stats = c.fetchall()
        
        conn.close()
        
        return jsonify({
            'total_cached': count,
            'total_size_mb': total_size / 1024 / 1024,
            'total_accesses': total_accesses,
            'cache_hits_saved': total_accesses,
            'by_platform': {p: {'count': c, 'size_mb': s/1024/1024} 
                           for p, c, s in platform_stats}
        }), 200
        
    except Exception as e:
        print(f"Cache stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'version': 'v3.0-cached',
        'yt_dlp_version': yt_dlp.version.__version__,
        'system': {
            'active_downloads': download_manager.active_count,
            'max_concurrent': download_manager.max_concurrent,
            'queue_size': download_queue.qsize(),
            'max_queue_size': download_queue.maxsize,
            'total_downloads': len(downloads)
        },
        'features': [
            'Video caching (no re-downloads)',
            'Audio extraction (MP3)',
            'Quality selection (360p-1080p)',
            'Ukrainian subtitles',
            'Mobile-optimized encoding',
            '7 platforms support'
        ],
        'supported_platforms': ['YouTube', 'Instagram', 'Twitter/X', 'Facebook', 'TikTok', 'Reddit', 'Pinterest']
    }), 200

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    try:
        active_downloads_gauge.set(download_manager.active_count)
        queue_size_gauge.set(download_queue.qsize())
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT SUM(file_size) FROM video_cache')
        result = c.fetchone()
        total_size = (result[0] or 0) / 1024 / 1024
        cache_size_gauge.set(total_size)
        conn.close()
        
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
    except Exception as e:
        print(f"Metrics error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'version': 'v3.0'}), 200

def cleanup_old_cache():
    """Очищаємо старий кеш"""
    while True:
        time.sleep(3600)
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            week_ago = time.time() - (7 * 24 * 60 * 60)
            c.execute('''SELECT file_path FROM video_cache 
                        WHERE downloaded_at < ? AND access_count < 2''', (week_ago,))
            
            old_files = c.fetchall()
            for (file_path,) in old_files:
                try:
                    Path(file_path).unlink(missing_ok=True)
                except:
                    pass
            
            c.execute('''DELETE FROM video_cache 
                        WHERE downloaded_at < ? AND access_count < 2''', (week_ago,))
            
            conn.commit()
            conn.close()
            print(f"🧹 Cache cleanup: removed {len(old_files)} old files")
            
        except Exception as e:
            print(f"Cache cleanup error: {e}")

def cleanup_old_downloads():
    """Очищаємо in-memory downloads"""
    while True:
        time.sleep(600)
        current_time = time.time()
        to_remove = []
        
        for download_id, data in downloads.items():
            if current_time - data.get('queued_at', current_time) > 3600:
                to_remove.append(download_id)
        
        for download_id in to_remove:
            downloads.pop(download_id, None)

# Ініціалізація
init_cache_db()
cleanup_cache_thread = threading.Thread(target=cleanup_old_cache, daemon=True)
cleanup_cache_thread.start()
cleanup_thread = threading.Thread(target=cleanup_old_downloads, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    print(f"🚀 Starting yt-dlp API v3.0 with yt-dlp {yt_dlp.version.__version__}")
    print("✅ Video caching enabled")
    print("✅ Audio extraction enabled")
    print("✅ Quality selection enabled")
    print("✅ Ukrainian subtitles enabled")
    app.run(host='0.0.0.0', port=8081, debug=False, threaded=True)
