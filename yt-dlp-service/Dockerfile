FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Встановлюємо найновіший yt-dlp
RUN pip install --no-cache-dir --upgrade yt-dlp flask requests

COPY app.py /app.py

WORKDIR /
EXPOSE 8081

CMD ["python", "/app.py"]
