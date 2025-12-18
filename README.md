# 🎥 Telegram Video Downloader Bot v4.0

Production-ready Telegram bot для завантаження відео з YouTube, TikTok, Instagram, Threads, Twitch та інших платформ.

## ✨ Features

### Core Features
- 🎯 **Auto-quality** - автоматично вибирає найкращу якість до 50MB
- 🖼 **Thumbnail preview** - показує прев'ю відео перед завантаженням
- 🔗 **Inline mode** - `@bot_username URL` працює в будь-якому чаті
- 🎵 Audio extraction (MP3)
- 📊 Quality selection (360p-1080p)
- ⚡ Smart cache (миттєві повторні завантаження)
- 👥 Group support (auto-download без тегів)
- 🍪 Instagram cookies support (приватні відео)

### v4.0 Architecture (NEW!)
- 🚀 **aiogram** - сучасний async бот фреймворк
- 🔄 **Celery + Redis** - розподілена черга задач
- 🌐 **Webhook mode** - замість polling для швидшого відгуку
- 🐘 **PostgreSQL** - надійне зберігання даних
- 📦 **MinIO** - S3-сумісне сховище для файлів
- 🌸 **Flower** - моніторинг воркерів
- 📊 **Real-time progress** - прогрес завантаження в реальному часі

## 🌐 Supported Platforms (9)

- YouTube / YouTube Shorts
- TikTok
- Instagram Reels / Stories
- Twitter/X
- Facebook
- Reddit
- Pinterest
- **Threads** (Meta)
- **Twitch Clips**

## 🚀 Quick Start

### v4.0 (Recommended for production)

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/telegram-video-bot.git
cd telegram-video-bot

# 2. Configure
cp .env.example .env
nano .env  # Add your TELEGRAM_BOT_TOKEN and other settings

# 3. Deploy v4.0
docker compose -f docker-compose.v4.yml up -d

# 4. Run migrations
docker compose -f docker-compose.v4.yml exec bot alembic upgrade head

# 5. Check logs
docker compose -f docker-compose.v4.yml logs -f
```

### v3.x (Legacy)

```bash
docker compose up -d
```

## 🏗 v4.0 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Telegram                              │
└────────────────────────────┬────────────────────────────────┘
                             │ Webhook
┌────────────────────────────▼────────────────────────────────┐
│                    aiogram Bot (8443)                        │
│                  - Webhook handler                           │
│                  - Rate limiting                             │
│                  - User tracking                             │
└────────────┬─────────────────────────────────┬──────────────┘
             │                                 │
┌────────────▼────────────┐     ┌──────────────▼──────────────┐
│      Redis (6379)       │     │     PostgreSQL (5432)       │
│   - Task queue          │     │   - Video cache             │
│   - Progress pub/sub    │     │   - User stats              │
│   - Rate limiting       │     │   - Download history        │
│   - Caching             │     │   - Group stats             │
└────────────┬────────────┘     └─────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────────┐
│                   Celery Workers                             │
│  ┌─────────────────────┐    ┌─────────────────────┐        │
│  │  Download Worker    │    │   Upload Worker     │        │
│  │  (queue: downloads) │    │  (queue: uploads)   │        │
│  │  concurrency: 2     │    │  concurrency: 3     │        │
│  └──────────┬──────────┘    └──────────┬──────────┘        │
└─────────────┼──────────────────────────┼────────────────────┘
              │                          │
┌─────────────▼──────────────────────────▼────────────────────┐
│                    yt-dlp Service                            │
│                  - Video download API                        │
│                  - Info extraction                           │
│                  - Format selection                          │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                   MinIO Storage (9000)                       │
│                  - S3-compatible storage                     │
│                  - /mnt/archive mount                        │
│                  - Downloaded videos                         │
└─────────────────────────────────────────────────────────────┘
```

## 📝 Configuration

### Environment Variables (v4.0)

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
WEBHOOK_URL=https://your-domain.com
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8443
ADMIN_IDS=123456789,987654321

# Database
DATABASE_URL=postgresql+asyncpg://videobot:password@postgres:5432/videobot

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# MinIO Storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=your_secure_password
MINIO_BUCKET=videos
MINIO_SECURE=false

# yt-dlp Service
YTDLP_SERVICE_URL=http://yt-dlp-api:8081

# Limits
MAX_FILE_SIZE=50000000
RATE_LIMIT_PER_MINUTE=10
```

### Docker Compose Services (v4.0)

| Service | Port | Description |
|---------|------|-------------|
| `bot` | 8443 | aiogram bot with webhook |
| `worker-download` | - | Celery download workers |
| `worker-upload` | - | Celery upload workers |
| `redis` | 6379 | Task queue & caching |
| `postgres` | 5432 | Persistent database |
| `minio` | 9000/9001 | S3-compatible storage |
| `flower` | 5555 | Celery monitoring |
| `yt-dlp-api` | 8081 | Video download API |

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
docker compose -f docker-compose.v4.yml restart
```

## 📊 Monitoring

### Flower Dashboard
Web UI для моніторингу Celery воркерів: `http://localhost:5555`

### MinIO Console
Web UI для керування файлами: `http://localhost:9001`

### Health Endpoints
- Bot health: `http://localhost:8443/health`
- Bot metrics: `http://localhost:8443/metrics`

## 📊 Performance

| Метрика | v3.x | v4.0 |
|---------|------|------|
| Response time | 5-10s | 2-5s |
| Cache hit | ~1s | ~0.5s |
| Max concurrent | 2 | 5+ |
| Scalability | Single server | Horizontal |
| Progress tracking | No | Real-time |

## 🎯 Commands

| Command | Description |
|---------|-------------|
| `/start` | Bot welcome message |
| `/help` | Detailed help |
| `/stats` | Your download statistics |
| `/settings` | Bot settings |
| `/admin` | Admin panel (admins only) |

## 👥 Group Usage

1. Add bot to group
2. Give admin rights (to delete service messages)
3. Send video URL - bot auto-downloads!

## 📋 Requirements

### v4.0 Production
- Docker & Docker Compose
- 8GB+ RAM (recommended)
- 4 CPU cores
- 50GB+ storage
- External storage mount for MinIO (`/mnt/archive`)

### v3.x Legacy
- Docker & Docker Compose
- 4GB+ RAM
- 10GB+ storage

## 🔄 Changelog

### v4.0 (current)
- 🚀 Complete architecture rewrite
- 🤖 aiogram instead of pyTelegramBotAPI
- 🔄 Celery + Redis for task queue
- 🌐 Webhook mode instead of polling
- 🐘 PostgreSQL instead of SQLite
- 📦 MinIO S3-compatible storage
- 📊 Real-time progress tracking
- 🌸 Flower monitoring dashboard
- ⚡ Horizontal scaling support

### v3.2
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

## 🔧 Migration from v3.x to v4.0

```bash
# 1. Stop v3.x
docker compose down

# 2. Backup data (optional)
cp -r downloads downloads_backup
cp -r bot_data bot_data_backup

# 3. Start v4.0
docker compose -f docker-compose.v4.yml up -d

# 4. Run migrations
docker compose -f docker-compose.v4.yml exec bot alembic upgrade head

# 5. Verify
docker compose -f docker-compose.v4.yml logs -f bot
```

## 📄 License

MIT License - see LICENSE file

## 🙏 Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [aiogram](https://github.com/aiogram/aiogram)
- [Celery](https://github.com/celery/celery)
- [MinIO](https://min.io/)
