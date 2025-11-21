# 🎥 Telegram Video Downloader Bot v3.0

Production-ready Telegram bot для завантаження відео з YouTube, TikTok, Instagram та інших платформ.

## ✨ Features

- 🎵 Audio extraction (MP3)
- 📊 Quality selection (360p-1080p)
- 🇺🇦 Ukrainian subtitles
- ⚡ Smart cache (миттєві повторні завантаження)
- 👥 Group support (auto-download без тегів)
- 📱 Mobile-friendly encoding
- 📊 Prometheus metrics
- 🛡️ Rate limiting (30s/user, 10s/group)

## 🌐 Supported Platforms

- YouTube / YouTube Shorts
- TikTok
- Instagram Reels
- Twitter/X
- Facebook
- Reddit
- Pinterest

## 🚀 Quick Start

1. Clone repository
git clone https://github.com/YOUR_USERNAME/telegram-video-bot.git
cd telegram-video-bot

2. Configure
cp .env.example .env
nano .env # Add your TELEGRAM_BOT_TOKEN

3. Deploy
docker compose up -d

4. Check logs
docker compose logs -f

text

## 📊 Performance

- Response time: 5-10s (first download)
- Cache hit: ~1s ⚡
- Max concurrent: 2 downloads
- Platforms: 7
- Cache efficiency: 85%+

## 🔧 Architecture

┌──────────────┐
│ Telegram Bot │
└──────┬───────┘
│
┌──────▼───────┐ ┌──────────┐
│ yt-dlp API │────►│ Redis │
└──────┬───────┘ │ Cache │
│ └──────────┘
┌──────▼───────┐
│ SQLite │
│ Database │
└──────────────┘

text

## 📝 Configuration

### Environment Variables

TELEGRAM_BOT_TOKEN=your_bot_token_here
YT_DLP_API_URL=http://yt-dlp-api:8081
MAX_FILE_SIZE=50000000

text

### Docker Compose

Services:
- `telegram-bot` - Telegram bot handler
- `yt-dlp-api` - Video download API
- `cleanup-service` - Auto cleanup old files

## 📊 Monitoring

Prometheus metrics endpoint: `http://localhost:8081/metrics`

Available metrics:
- `downloads_total` - Total downloads by platform
- `cache_hits_total` - Cache hit count
- `cache_misses_total` - Cache miss count
- `active_downloads` - Currently active downloads
- `queue_size` - Download queue size
- `cache_size_mb` - Cache size in MB

## 🎯 Commands

- `/start` - Bot welcome message
- `/audio [URL]` - Download audio only (MP3)
- `/stats` - Cache statistics
- `/group_help` - Help for group usage

## 👥 Group Usage

1. Add bot to group
2. Give admin rights (to delete service messages)
3. Send video URL - bot auto-downloads!

## 📋 Requirements

- Docker & Docker Compose
- 4GB+ RAM
- 10GB+ storage

## 🔄 Versions

- **v3.0** (current) - Smart cache, groups, metrics
- **v2.0** - Audio extraction, quality selection
- **v1.0** - Basic video download

## 📄 License

MIT License - see LICENSE file

## 👤 Author

Your Name (@your_telegram)

## 🙏 Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI)
