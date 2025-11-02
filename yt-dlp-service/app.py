from flask import Flask, request, jsonify
import yt_dlp
import os
import threading
import time
import uuid
from pathlib import Path

app = Flask(__name__)

# Словник для відстеження завантажень
downloads = {}

@app.route('/add', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    # Генеруємо унікальний ID для завантаження
    download_id = str(uuid.uuid4())
    downloads[download_id] = {
        'status': 'queued',
        'url': url,
        'file_path': None,
        'error': None
    }
    
    # Запускаємо завантаження в окремому потоці
    thread = threading.Thread(target=download_worker, args=(url, download_id))
    thread.start()
    
    return jsonify({'status': 'queued', 'url': url, 'id': download_id}), 200

@app.route('/status/<download_id>', methods=['GET'])
def get_status(download_id):
    if download_id in downloads:
        return jsonify(downloads[download_id]), 200
    else:
        return jsonify({'error': 'Download not found'}), 404

def download_worker(url, download_id):
    try:
        downloads[download_id]['status'] = 'downloading'
        
        # Налаштування yt-dlp з cookies та headers для Instagram
        ydl_opts = {
            'outtmpl': f'/downloads/{download_id}_%(title)s.%(ext)s',
            'format': 'best[height<=720]/best',
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': False,
            # Додаткові налаштування для Instagram
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Отримуємо інформацію про відео
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
            
            downloads[download_id]['title'] = title
            downloads[download_id]['status'] = 'downloading'
            
            # Завантажуємо відео
            ydl.download([url])
            
            # Знаходимо завантажений файл
            download_dir = Path('/downloads')
            for file_path in download_dir.glob(f"{download_id}_*"):
                if file_path.is_file():
                    downloads[download_id]['file_path'] = str(file_path)
                    downloads[download_id]['status'] = 'completed'
                    return
            
            downloads[download_id]['status'] = 'error'
            downloads[download_id]['error'] = 'File not found after download'
            
    except Exception as e:
        downloads[download_id]['status'] = 'error'  
        downloads[download_id]['error'] = str(e)
        print(f"Error downloading {url}: {e}")

@app.route('/', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'active_downloads': len([d for d in downloads.values() if d['status'] == 'downloading']),
        'total_downloads': len(downloads)
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=True)
