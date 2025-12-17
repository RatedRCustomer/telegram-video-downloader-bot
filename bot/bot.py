import os
import requests
import telebot
import time
import logging
import validators
import subprocess
import json
from pathlib import Path
from telebot import types
from collections import defaultdict


def get_video_metadata(file_path):
    """Отримує метадані відео (ширина, висота, тривалість) через ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    width = stream.get('width', 0)
                    height = stream.get('height', 0)
                    duration = float(data.get('format', {}).get('duration', 0))
                    return {
                        'width': width,
                        'height': height,
                        'duration': int(duration)
                    }
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to get video metadata: {e}")
    return None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
YT_DLP_API_URL = os.getenv('YT_DLP_API_URL', 'http://yt-dlp-api:8081')
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 50000000))

bot = telebot.TeleBot(TOKEN)

SUPPORTED_DOMAINS = [
    'tiktok.com', 'vm.tiktok.com',
    'instagram.com', 
    'youtube.com', 'youtu.be',
    'twitter.com', 'x.com',
    'facebook.com', 'fb.watch',
    'reddit.com', 'redd.it',
    'pinterest.com', 'pin.it'
]

# Rate limiting для груп
user_last_request = defaultdict(float)
group_last_request = defaultdict(float)
user_urls = {}

def is_rate_limited(message):
    """Перевіряє rate limiting"""
    current_time = time.time()
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Для користувачів - 1 запит на 30 секунд
    if current_time - user_last_request[user_id] < 30:
        return True
    
    # Для груп - 1 запит на 10 секунд
    if message.chat.type in ['group', 'supergroup']:
        if current_time - group_last_request[chat_id] < 10:
            return True
        group_last_request[chat_id] = current_time
    
    user_last_request[user_id] = current_time
    return False

def is_supported_url(url):
    if not validators.url(url):
        return False
    return any(domain in url.lower() for domain in SUPPORTED_DOMAINS)

def extract_urls_from_message(text):
    """Витягує всі URL з повідомлення"""
    words = text.split()
    urls = [word for word in words if is_supported_url(word)]
    return urls

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🎥 *Telegram Video Downloader Bot v3.1*

Надішліть посилання і оберіть параметри!

✅ *Підтримувані платформи:*
• YouTube/Shorts (з субтитрами 🇺🇦)
• TikTok
• Instagram Reels
• Twitter/X (тільки пости з відео)
• Facebook
• Reddit
• Pinterest

🎛️ *Можливості:*
• 🎵 Audio-only (MP3)
• 📊 Вибір якості (360p-1080p)
• 🇺🇦 Українські субтитри
• ⚡ Smart cache (миттєво!)
• 👥 Працює в групах!
• 📐 Збереження оригінального формату

📋 *Обмеження:*
• Max файл: 50MB
• Rate limit: 30s/user, 10s/group

*Команди:*
/audio - тільки аудіо
/stats - статистика кешу
/group_help - довідка для груп

Просто надішліть посилання! ⏳
"""
    try:
        bot.reply_to(message, welcome_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Welcome message error: {e}")
        # Fallback без Markdown
        bot.reply_to(message, welcome_text.replace('*', ''))

@bot.message_handler(commands=['group_help'])
def group_help(message):
    """Спеціальна довідка для груп"""
    help_text = """
👥 **Bot у групі:**

✅ **Автоматичне завантаження:**
Просто надішліть посилання - бот автоматично завантажить відео!

⚙️ **Для опцій (якість/аудіо):**
• Reply на посилання і напишіть `/audio`
• Або використайте inline buttons в приватному чаті

⏰ **Обмеження:**
• 30 сек між запитами (користувач)
• 10 сек між запитами (група)
• Max 50MB файли

✅ **Підтримуються:** YouTube, TikTok, Instagram, Twitter, Facebook, Reddit, Pinterest

⚡ Cache економить час - повторні запити миттєві!
"""
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['audio', 'mp3'])
def handle_audio_command(message):
    """Команда для завантаження аудіо"""
    try:
        # Витягуємо URL з команди або reply
        if message.reply_to_message and message.reply_to_message.text:
            urls = extract_urls_from_message(message.reply_to_message.text)
        else:
            parts = message.text.split(' ', 1)
            urls = extract_urls_from_message(parts[1]) if len(parts) > 1 else []
        
        if not urls:
            bot.reply_to(message, "❌ URL не знайдено. Використання: /audio https://youtube.com/...")
            return
        
        if is_rate_limited(message):
            bot.reply_to(message, "⏰ Зачекайте 30 секунд перед наступним запитом")
            return
        
        # В групах - автоматично audio без кнопок
        if message.chat.type in ['group', 'supergroup']:
            download_content(message, urls[0], quality='720p', format='audio')
        else:
            # В приватних чатах - показуємо кнопки
            user_urls[message.from_user.id] = urls[0]
            download_content(message, urls[0], quality='720p', format='audio')
        
    except Exception as e:
        logger.error(f"Audio command error: {e}")
        bot.reply_to(message, "❌ Помилка обробки команди")

@bot.message_handler(commands=['stats'])
def show_cache_stats(message):
    """Показує статистику кешу"""
    try:
        response = requests.get(f"{YT_DLP_API_URL}/cache/stats", timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            stats_text = f"""
📊 **Статистика кешу**

💾 **Всього:**
• Відео в кеші: {data['total_cached']}
• Розмір: {data['total_size_mb']:.2f} MB
• Cache hits: {data['cache_hits_saved']}

📈 **По платформам:**
"""
            for platform, stats in data.get('by_platform', {}).items():
                stats_text += f"• {platform}: {stats['count']} ({stats['size_mb']:.2f} MB)\n"
            
            stats_text += "\n⚡ Cache hits економить час і трафік!"
            
            bot.reply_to(message, stats_text, parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ Не вдалося отримати статистику")
    except Exception as e:
        logger.error(f"Stats error: {e}")
        bot.reply_to(message, "❌ Помилка з'єднання з API")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Обробка всіх повідомлень (приватні + групи)"""
    urls = extract_urls_from_message(message.text)
    
    if not urls:
        return
    
    # Rate limiting
    if is_rate_limited(message):
        if message.chat.type == 'private':
            bot.reply_to(message, "⏰ Зачекайте 30 секунд перед наступним запитом")
        return
    
    url = urls[0]
    
    # В ГРУПАХ - автоматичне завантаження БЕЗ кнопок (720p video)
    if message.chat.type in ['group', 'supergroup']:
        logger.info(f"Group request from {message.chat.title}: {url}")
        download_content(message, url, quality='720p', format='video', show_buttons=False)
        return
    
    # В ПРИВАТНИХ ЧАТАХ - показуємо inline buttons
    user_urls[message.from_user.id] = url
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎥 720p (рекомендовано)", callback_data="quality_720_video"),
        types.InlineKeyboardButton("💎 1080p", callback_data="quality_1080_video")
    )
    markup.add(
        types.InlineKeyboardButton("📱 480p (мобільні)", callback_data="quality_480_video"),
        types.InlineKeyboardButton("⚡ 360p (швидко)", callback_data="quality_360_video")
    )
    markup.add(
        types.InlineKeyboardButton("🎵 Аудіо (MP3)", callback_data="quality_audio_audio")
    )
    
    bot.reply_to(message, "⚙️ Оберіть формат завантаження:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_quality_callback(call):
    """Обробка вибору якості"""
    try:
        parts = call.data.split('_')
        quality = parts[1] + 'p' if parts[2] == 'video' else parts[1]
        format = parts[2]
        
        user_id = call.from_user.id
        url = user_urls.get(user_id)
        
        if not url:
            bot.answer_callback_query(call.id, "❌ URL не знайдено. Надішліть заново.")
            return
        
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        
        quality_text = {
            'audio': '🎵 MP3 аудіо',
            '360p': '⚡ 360p відео',
            '480p': '📱 480p відео',
            '720p': '🎥 720p відео',
            '1080p': '💎 1080p відео'
        }.get(quality, quality)
        
        bot.answer_callback_query(call.id, f"✅ Обрано: {quality_text}")
        download_content(call.message, url, quality, format, show_buttons=True)
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Помилка")

def download_content(message, url, quality='720p', format='video', show_buttons=False):
    """Завантажує контент з обраними параметрами"""
    status_msg = bot.reply_to(message, "⏳ Перевіряю кеш...")

    try:
        logger.info(f"Request: {url} (quality={quality}, format={format})")
        response = requests.post(
            f"{YT_DLP_API_URL}/add",
            json={"url": url, "quality": quality, "format": format},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            
            # CACHE HIT!
            if data.get('cached'):
                logger.info(f"✅ CACHE HIT for {url}")
                
                cache_emoji = '⚡'
                if message.chat.type in ['group', 'supergroup']:
                    cache_emoji = '💾'  # В групах інша емодзі
                
                bot.edit_message_text(
                    f"{cache_emoji} Кеш! Відправляю...",
                    message.chat.id,
                    status_msg.message_id
                )
                
                send_file_from_cache(message, data, status_msg)
                return
            
            download_id = data.get('id')
            logger.info(f"Queued: {download_id}")
            
            format_emoji = '🎵' if format == 'audio' else '🎥'
            bot.edit_message_text(
                f"{format_emoji} Завантажую {quality}...",
                message.chat.id,
                status_msg.message_id
            )

            # Polling
            for i in range(36):
                time.sleep(5)
                
                status_response = requests.get(f"{YT_DLP_API_URL}/status/{download_id}", timeout=5)
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    
                    if status_data['status'] == 'completed':
                        send_downloaded_content(message, status_data, status_msg)
                        return
                        
                    elif status_data['status'] == 'error':
                        error_msg = status_data.get('error', 'Unknown error')

                        # Форматуємо повідомлення про помилку залежно від типу
                        if 'немає відео' in error_msg.lower() or 'no video' in error_msg.lower():
                            display_msg = "📝 Цей пост не містить відео"
                        elif 'не вдалося' in error_msg.lower():
                            display_msg = f"❌ {error_msg}"
                        else:
                            display_msg = f"❌ Помилка: {error_msg[:100]}"

                        bot.edit_message_text(
                            display_msg,
                            message.chat.id,
                            status_msg.message_id
                        )
                        return
                
                if i % 3 == 0 and i > 0:
                    dots = "." * ((i // 3) % 4)
                    bot.edit_message_text(
                        f"{format_emoji} Обробляю{dots} ({i*5}s)",
                        message.chat.id,
                        status_msg.message_id
                    )

            bot.edit_message_text(
                "⏰ Таймаут. Спробуйте ще раз.",
                message.chat.id,
                status_msg.message_id
            )

        elif response.status_code == 429:
            bot.edit_message_text(
                "⏸️ Сервер зайнятий. Зачекайте хвилину.",
                message.chat.id,
                status_msg.message_id
            )

    except Exception as e:
        logger.error(f"Error: {e}")
        bot.edit_message_text(
            "❌ Помилка. Спробуйте ще раз.",
            message.chat.id,
            status_msg.message_id
        )

def send_file_from_cache(message, data, status_msg):
    """Відправляє файл з кешу"""
    try:
        file_path = Path(data['file_path'])
        format = data.get('format', 'video')

        if not file_path.exists():
            bot.edit_message_text("❌ Кеш файл не знайдено", message.chat.id, status_msg.message_id)
            return

        # В групах - мінімум тексту
        if message.chat.type in ['group', 'supergroup']:
            bot.edit_message_text("📤 Відправляю...", message.chat.id, status_msg.message_id)
        else:
            bot.edit_message_text("📤 Відправляю з кешу...", message.chat.id, status_msg.message_id)

        caption = f"⚡ Кеш" if message.chat.type in ['group', 'supergroup'] else f"🎵 {data['title']}\n\n⚡ Кеш"

        if format == 'audio':
            with open(file_path, 'rb') as audio:
                bot.send_audio(
                    message.chat.id,
                    audio,
                    caption=caption,
                    reply_to_message_id=message.message_id
                )
        else:
            # Отримуємо метадані відео для коректного відображення
            metadata = get_video_metadata(file_path)
            with open(file_path, 'rb') as video:
                send_kwargs = {
                    'chat_id': message.chat.id,
                    'video': video,
                    'caption': caption,
                    'reply_to_message_id': message.message_id,
                    'supports_streaming': True
                }
                if metadata:
                    send_kwargs['width'] = metadata['width']
                    send_kwargs['height'] = metadata['height']
                    send_kwargs['duration'] = metadata['duration']
                bot.send_video(**send_kwargs)

        bot.delete_message(message.chat.id, status_msg.message_id)
        logger.info(f"✅ Sent from cache: {data.get('url', 'unknown')}")

    except Exception as e:
        logger.error(f"Cache send error: {e}")
        bot.edit_message_text("❌ Помилка відправки", message.chat.id, status_msg.message_id)

def send_downloaded_content(message, status_data, status_msg):
    """Відправляє новозавантажений контент"""
    file_path = Path(status_data.get('file_path'))
    if not file_path.exists():
        bot.edit_message_text("❌ Файл не знайдено", message.chat.id, status_msg.message_id)
        return

    try:
        file_size = file_path.stat().st_size
        title = status_data.get('title', 'Video')
        format = status_data.get('format', 'video')

        if file_size > MAX_FILE_SIZE:
            bot.edit_message_text(
                f"❌ Файл завеликий ({file_size // 1024 // 1024}MB). Max: 50MB",
                message.chat.id,
                status_msg.message_id
            )
            return

        bot.edit_message_text("📤 Відправляю...", message.chat.id, status_msg.message_id)

        # В групах - короткий caption
        if message.chat.type in ['group', 'supergroup']:
            caption = f"✅ Готово"
        else:
            caption = f"{'🎵' if format == 'audio' else '🎥'} {title}"

        if format == 'audio':
            with open(file_path, 'rb') as audio:
                bot.send_audio(
                    message.chat.id,
                    audio,
                    caption=caption,
                    reply_to_message_id=message.message_id
                )
        else:
            # Отримуємо метадані відео для коректного відображення
            metadata = get_video_metadata(file_path)
            with open(file_path, 'rb') as video:
                send_kwargs = {
                    'chat_id': message.chat.id,
                    'video': video,
                    'caption': caption,
                    'reply_to_message_id': message.message_id,
                    'supports_streaming': True
                }
                if metadata:
                    send_kwargs['width'] = metadata['width']
                    send_kwargs['height'] = metadata['height']
                    send_kwargs['duration'] = metadata['duration']
                bot.send_video(**send_kwargs)

        bot.delete_message(message.chat.id, status_msg.message_id)
        logger.info(f"✅ Sent: {status_data.get('url', 'unknown')}")

    except Exception as e:
        logger.error(f"Send error: {e}")
        bot.edit_message_text("❌ Помилка відправки", message.chat.id, status_msg.message_id)

if __name__ == '__main__':
    logger.info("🚀 Starting Telegram Video Bot v3.1 (Groups enabled)...")
    logger.info(f"API URL: {YT_DLP_API_URL}")
    
    try:
        response = requests.get(f"{YT_DLP_API_URL}/health", timeout=5)
        logger.info("✅ YT-DLP API accessible")
    except:
        logger.warning("⚠️ YT-DLP API not accessible yet")

    bot.polling(none_stop=True, interval=0, timeout=60)
