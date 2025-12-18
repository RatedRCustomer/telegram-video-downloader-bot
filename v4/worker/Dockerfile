FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (ffmpeg for video processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared /app/shared

# Copy worker code
COPY worker /app/worker

# Create directories
RUN mkdir -p /downloads /cookies

WORKDIR /app/worker

# Default command (can be overridden in docker-compose)
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]
