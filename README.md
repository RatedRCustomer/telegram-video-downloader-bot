# Telegram Video Downloader Bot

Власний Telegram бот для завантаження відео з популярних платформ:

- 🎵 TikTok
- 📸 Instagram Reels/Posts  
- ▶️ YouTube/YouTube Shorts
- 🐦 Twitter/X
- 📘 Facebook
- 🤖 Reddit

## Архітектура

- **Backend**: yt-dlp API (Flask)
- **Frontend**: Telegram Bot (pyTelegramBotAPI)
- **Infrastructure**: Docker Compose
- **Storage**: SSD на Raspberry Pi 4

## Запуск

1. Створіть бота в [@BotFather](https://t.me/BotFather)
2. Скопіюйте `.env.example` в `.env` та додайте токен
3. Запустіть: `docker compose up -d`

## Особливості

- ✅ Підтримка 9+ платформ
- ✅ Автоматичне стиснення до 50MB
- ✅ Якість до 720p для економії трафіку
- ✅ Логування та моніторинг
- ✅ Працює на ARM64 (Raspberry Pi)

Розроблено для домашнього використання на Raspberry Pi 4 з SSD.
