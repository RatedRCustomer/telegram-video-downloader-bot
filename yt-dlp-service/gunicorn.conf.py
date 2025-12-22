import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8081"
backlog = 2048

# Workers
workers = int(os.getenv('WORKERS', 4))
worker_class = 'gthread'  # Threads для I/O-bound tasks (yt-dlp)
threads = 2
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 600  # 10 min для довгих завантажень
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "telegram-yt-dlp-api"

# Server mechanics
daemon = False
pidfile = None
