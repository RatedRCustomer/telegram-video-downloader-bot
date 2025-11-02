import os
import requests
import telebot
import time
import json
import logging
import validators
from pathlib import Path
from telebot import types
import threading

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфігурація
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
YT_DLP_API_URL = os.getenv('YT_DLP_API_URL', 'http://yt-dlp-api:8081')
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 50000000))  # 50MB
DOWNLOAD_PATH = '/downloads'

bot = telebot.TeleBot(TOKEN)

# Підтримувані домени
SUPPORTED_DOMAINS = [
    'tiktok.com',
    'instagram.com', 
    'youtube.com',
    'youtu.be',
    'twitter.com',
    'x.com',
    'facebook.com',
    'fb.watch',
    'reddit.com'
]

def is_supported_url(url):
    """Перевіряє чи підтримується URL"""
    if not validators.url(url):
        return False
    
    return any(domain in url.lower() for domain in SUPPORTED_DOMAINS)

def download_video(url):
    """Завантажує відео через yt-dlp API"""
    try:
        # Додаємо завдання до черги
        response = requests.post(
            f"{YT_DLP_API_URL}/add",
            json={
                "url": url,
                "quality": "best[height<=720]",  # Обмежуємо якість для економії
                "format": "mp4"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"Successfully queued download for: {url}")
            return True
        else:
            logger.error(f"Failed to queue download: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        return False

def find_downloaded_file(url):
    """Шукає завантажений файл"""
    downloads = Path(DOWNLOAD_PATH)
    
    # Шукаємо файли які були створені в останні 5 хвилин
    recent_files = []
    for file_path in downloads.glob("*"):
        if file_path.is_file() and time.time() - file_path.stat().st_mtime < 300:
            recent_files.append(file_path)
    
    # Повертаємо найновіший файл
    if recent_files:
        return max(recent_files, key=lambda x: x.stat().st_mtime)
    
    return None

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Команда привітання"""
    welcome_text = """
🎥 **Telegram Video Downloader Bot**

Надішліть мені посилання на відео і я завантажу його для вас!

**Підтримувані платформи:**
• TikTok
• Instagram Reels/Posts  
• YouTube/YouTube Shorts
• Twitter/X
• Facebook
• Reddit

**Обмеження:**
• Максимальний розмір файлу: 50MB
• Підтримується тільки відео контент

Просто надішліть посилання і чекайте! ⏳
    """
    
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_url(message):
    """Обробка URL від користувача"""
    url = message.text.strip()
    
    # Перевіряємо валідність URL
    if not is_supported_url(url):
        bot.reply_to(
            message, 
            "❌ Будь ласка, надішліть валідне посилання на відео з підтримуваних платформ:\n"
            "TikTok, Instagram, YouTube, Twitter/X, Facebook, Reddit"
        )
        return
    
    # Повідомляємо про початок завантаження
    status_msg = bot.reply_to(message, "⏳ Завантажую відео, зачекайте...")
    
    try:
        # Завантажуємо відео через новий API
        response = requests.post(
            f"{YT_DLP_API_URL}/add",
            json={"url": url},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            download_id = data.get('id')
            
            bot.edit_message_text(
                "📥 Відео додано до черги. Обробляю...",
                message.chat.id,
                status_msg.message_id
            )
            
            # Чекаємо завантаження (максимум 3 хвилини)
            for i in range(36):  # 36 * 5 секунд = 3 хвилини
                time.sleep(5)
                
                # Перевіряємо статус завантаження
                status_response = requests.get(f"{YT_DLP_API_URL}/status/{download_id}")
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    
                    if status_data['status'] == 'completed':
                        file_path = Path(status_data['file_path'])
                        
                        if file_path.exists():
                            # Перевіряємо розмір файлу
                            if file_path.stat().st_size > MAX_FILE_SIZE:
                                bot.edit_message_text(
                                    f"❌ Файл занадто великий ({file_path.stat().st_size // 1024 // 1024}MB). "
                                    f"Максимум: {MAX_FILE_SIZE // 1024 // 1024}MB",
                                    message.chat.id,
                                    status_msg.message_id
                                )
                                file_path.unlink(missing_ok=True)
                                return
                            
                            # Відправляємо файл
                            bot.edit_message_text(
                                "📤 Відправляю відео...",
                                message.chat.id,
                                status_msg.message_id
                            )
                            
                            with open(file_path, 'rb') as video:
                                bot.send_video(
                                    message.chat.id,
                                    video,
                                    caption=f"🎥 {status_data.get('title', 'Завантажене відео')}\n\n📎 {url}",
                                    reply_to_message_id=message.message_id
                                )
                            
                            # Видаляємо статусне повідомлення та файл
                            bot.delete_message(message.chat.id, status_msg.message_id)
                            file_path.unlink(missing_ok=True)
                            
                            logger.info(f"Successfully sent video for URL: {url}")
                            return
                        
                    elif status_data['status'] == 'error':
                        bot.edit_message_text(
                            f"❌ Помилка завантаження: {status_data.get('error', 'Unknown error')}",
                            message.chat.id,
                            status_msg.message_id
                        )
                        return
                
                # Оновлюємо статус кожні 15 секунд
                if i % 3 == 0:
                    dots = "." * ((i // 3) % 4)
                    bot.edit_message_text(
                        f"⏳ Обробляю відео{dots}",
                        message.chat.id,
                        status_msg.message_id
                    )
            
            # Таймаут
            bot.edit_message_text(
                "⏰ Час очікування вичерпано. Відео можливо завантажилося, спробуйте ще раз.",
                message.chat.id,
                status_msg.message_id
            )
            
        else:
            bot.edit_message_text(
                "❌ Не вдалося додати відео до черги завантаження.",
                message.chat.id,
                status_msg.message_id
            )
            
    except Exception as e:
        logger.error(f"Error processing URL {url}: {str(e)}")
        bot.edit_message_text(
            "❌ Виникла помилка при обробці відео. Спробуйте ще раз.",
            message.chat.id,
            status_msg.message_id
        )


if __name__ == '__main__':
    logger.info("Starting Telegram Video Bot...")
    logger.info(f"API URL: {YT_DLP_API_URL}")
    
    # Перевіряємо доступність API
    try:
        response = requests.get(f"{YT_DLP_API_URL}", timeout=5)
        logger.info("YT-DLP API is accessible")
    except:
        logger.warning("YT-DLP API is not accessible yet")
    
    # Запускаємо бота
    bot.polling(none_stop=True, interval=0, timeout=60)
