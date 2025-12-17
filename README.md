# 🎥 Telegram Video Downloader Bot v3.2

Production-ready Telegram bot для завантаження відео з YouTube, TikTok, Instagram, Threads, Twitch та інших платформ.

## ✨ Features

- 🎯 **Auto-quality** - автоматично вибирає найкращу якість до 50MB
- 🖼 **Thumbnail preview** - показує прев'ю відео перед завантаженням
- 🔗 **Inline mode** - `@bot_username URL` працює в будь-якому чаті
- 🎵 Audio extraction (MP3)
- 📊 Quality selection (360p-1080p)
- 🇺🇦 Ukrainian subtitles
- ⚡ Smart cache (миттєві повторні завантаження)
- 👥 Group support (auto-download без тегів)
- 🍪 Instagram cookies support (приватні відео)
- 📊 Prometheus metrics
- 🛡️ Rate limiting (30s/user, 10s/group)

## 🌐 Supported Platforms (9)

- YouTube / YouTube Shorts
- TikTok
- Instagram Reels
- Twitter/X
- Facebook
- Reddit
- Pinterest
- **Threads** (Meta) 🆕
- **Twitch Clips** 🆕

## 🚀 Quick Start

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/telegram-video-bot.git
cd telegram-video-bot

# 2. Configure
cp .env.example .env
nano .env  # Add your TELEGRAM_BOT_TOKEN

# 3. Deploy
docker compose up -d

# 4. Check logs
docker compose logs -f
```

## 🔗 Inline Mode

Використовуйте бота в будь-якому чаті:

```
@your_bot_username https://www.youtube.com/watch?v=...
```

Оберіть якість з меню:
- 🎯 Auto (рекомендовано) - найкраща якість до 50MB
- 🎥 720p HD
- 💎 1080p Full HD
- 🎵 Audio only (MP3)

## 🍪 Instagram Cookies (Optional)

Для завантаження приватних Instagram відео:

1. Експортуйте cookies з браузера (розширення "Get cookies.txt")
2. Збережіть як `downloads/cookies.txt`
3. Перезапустіть контейнери

```bash
docker compose restart
```

## 📊 Performance

| Метрика | Значення |
|---------|----------|
| Response time | 5-10s (first download) |
| Cache hit | ~1s ⚡ |
| Max concurrent | 2 downloads |
| Platforms | 9 |
| Cache efficiency | 85%+ |

## 🔧 Architecture

```
┌──────────────────┐
│   Telegram Bot   │
│   (Inline mode)  │
└────────┬─────────┘
         │
┌────────▼─────────┐     ┌──────────┐
│   yt-dlp API     │────►│  SQLite  │
│  (Auto-quality)  │     │  Cache   │
└────────┬─────────┘     └──────────┘
         │
┌────────▼─────────┐
│    Downloads     │
│    /downloads    │
└──────────────────┘
```

## 📝 Configuration

### Environment Variables

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
YT_DLP_API_URL=http://yt-dlp-api:8081
MAX_FILE_SIZE=50000000
```

### Docker Compose Services

| Service | Description |
|---------|-------------|
| `telegram-bot` | Telegram bot handler |
| `yt-dlp-api` | Video download API |
| `cleanup-service` | Auto cleanup old files |

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

| Command | Description |
|---------|-------------|
| `/start` | Bot welcome message |
| `/audio [URL]` | Download audio only (MP3) |
| `/stats` | Cache statistics |
| `/group_help` | Help for group usage |

## 👥 Group Usage

1. Add bot to group
2. Give admin rights (to delete service messages)
3. Send video URL - bot auto-downloads!

## 📋 Requirements

- Docker & Docker Compose
- 4GB+ RAM
- 10GB+ storage

## 🔄 Changelog

### v3.2 (current)
- ✨ Inline mode - use bot in any chat
- 🎯 Auto-quality selection (best under 50MB)
- 🖼 Thumbnail preview before download
- 🆕 Threads (Meta) support
- 🆕 Twitch Clips support
- 🍪 Instagram cookies support

### v3.1
- 🔧 Fixed Story chat error (pyTelegramBotAPI update)
- 🐦 Twitter video pre-check
- 📐 Original format preserved (no re-encoding)

### v3.0
- Smart cache, groups, metrics

### v2.0
- Audio extraction, quality selection

### v1.0
- Basic video download

## 📄 License

MIT License - see LICENSE file

## 🙏 Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI)
- [gallery-dl](https://github.com/mikf/gallery-dl)
