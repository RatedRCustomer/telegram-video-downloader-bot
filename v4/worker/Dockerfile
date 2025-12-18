FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p /downloads /cookies

# Run as non-root
RUN useradd -m worker && chown -R worker:worker /app /downloads
USER worker

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]
