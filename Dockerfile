FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    HOST=0.0.0.0 \
    AUTO_OPEN_BROWSER=0 \
    WHISPER_ENABLED=0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    fontconfig \
    fonts-dejavu-core \
    fonts-noto-core \
    fonts-noto-extra \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN mkdir -p audio outputs data background_audio vision

EXPOSE 7860

CMD gunicorn --workers 1 --threads 4 --timeout 900 --bind 0.0.0.0:${PORT} main:app
