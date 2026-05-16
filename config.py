"""
Configuration file for Quran Reels Video Generator
"""

import os

# Base directories
# For EXE: We want persistent files next to the EXE, not in temp _MEIPASS
import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VISION_DIR = os.path.join(BASE_DIR, 'vision')
AUDIO_DIR = os.path.join(BASE_DIR, 'audio')
OUTPUTS_DIR = os.path.join(BASE_DIR, 'outputs')
DATA_DIR = os.path.join(BASE_DIR, 'data')
BACKGROUND_AUDIO_DIR = os.path.join(BASE_DIR, 'background_audio')


def _load_local_env():
    """Load simple KEY=VALUE pairs from .env (without overriding existing env vars)."""
    env_path = os.path.join(BASE_DIR, '.env')
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # Non-fatal: app can still run with system environment variables.
        pass


_load_local_env()

# FFmpeg and ImageMagick paths
FFMPEG_PATH = "ffmpeg"
IMAGEMAGICK_PATH = "magick"

# Video settings
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280
VIDEO_FPS = 30
MAX_WORDS_PER_CHUNK = 5  # Maximum number of words to display at once
FADE_DURATION = 0.2      # Duration of fade in/out in seconds (Faster for better sync)

# Audio settings
AUDIO_FORMAT = "mp3"
AUDIO_SAMPLE_RATE = 44100

# Audio synchronization settings
AVERAGE_SPEECH_RATE = 2.5  # Average words per second for Quranic recitation
SILENCE_THRESHOLD = -40  # dB threshold for silence detection
MIN_SILENCE_DURATION = 0.1  # Minimum silence duration in seconds to be considered a pause
WHISPER_ENABLED = os.getenv("WHISPER_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base").strip() or "base"

# Text overlay settings
TEXT_COLOR = "white"
TASHKEEL_COLOR = "#FFD700"  # Gold color for diacritics
TEXT_FONT_SIZE = 43         # Reduced again to prevent word wrapping
TEXT_FONT = "Traditional Arabic"  # Better font for Quranic text on Windows
TEXT_STROKE_COLOR = "black"
TEXT_STROKE_WIDTH = 2       # Thinner stroke for Uthmani text
TEXT_SHADOW = True
TEXT_POSITION = "center"
TRANSLATION_FONT_SIZE = 20  # Reduced again for better fit

# Background settings
BACKGROUND_OPACITY = 0.3

# API URLs
EVERYAYAH_BASE_URL = "https://everyayah.com"
ALQURAN_API_BASE_URL = "https://api.alquran.cloud/v1"
RECITERS_JSON_URL = "http://www.everyayah.com/data/status.json"

# SEO / Metadata generation settings
SEO_ENABLED = os.getenv("SEO_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
SEO_TIMEOUT_SEC = int(os.getenv("SEO_TIMEOUT_SEC", "30"))
SEO_MAX_RETRIES = int(os.getenv("SEO_MAX_RETRIES", "2"))

# Create directories if they don't exist
for directory in [VISION_DIR, AUDIO_DIR, OUTPUTS_DIR, DATA_DIR, BACKGROUND_AUDIO_DIR]:
    os.makedirs(directory, exist_ok=True)
