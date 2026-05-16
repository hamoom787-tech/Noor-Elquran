"""
Configuration file for Quran Reels Video Generator
"""

import os
import sys
import platform

# Detect if running on mobile (BeeWare)
IS_MOBILE = hasattr(sys, 'getandroidapilevel') or 'iOS' in str(sys.platform) or os.environ.get('BRIEFCASE_APP_NAME')
IS_ANDROID = hasattr(sys, 'getandroidapilevel') or platform.system() == 'Android'
IS_IOS = 'iOS' in str(sys.platform) or platform.system() == 'Darwin' and IS_MOBILE

# Base directories
# For EXE: We want persistent files next to the EXE, not in temp _MEIPASS
# For Mobile: Use app-specific directories
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
elif IS_MOBILE:
    # For mobile apps, use app-specific directories
    if IS_ANDROID:
        # Android: Use app's external storage
        try:
            from android.storage import primary_external_storage_path
            BASE_DIR = primary_external_storage_path()
        except:
            BASE_DIR = os.path.expanduser("~")
    elif IS_IOS:
        # iOS: Use app's documents directory
        BASE_DIR = os.path.expanduser("~/Documents")
    else:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory setup
VISION_DIR = os.path.join(BASE_DIR, 'vision')
AUDIO_DIR = os.path.join(BASE_DIR, 'audio')
OUTPUTS_DIR = os.path.join(BASE_DIR, 'outputs')
DATA_DIR = os.path.join(BASE_DIR, 'data')

# FFmpeg path - handle mobile platforms
if IS_MOBILE:
    if IS_ANDROID:
        # Android: FFmpeg should be in assets or bundled
        FFMPEG_PATH = os.path.join(BASE_DIR, 'app', 'src', 'main', 'assets', 'ffmpeg')
        if not os.path.exists(FFMPEG_PATH):
            # Fallback to system path
            FFMPEG_PATH = "ffmpeg"
    elif IS_IOS:
        # iOS: FFmpeg should be in app bundle
        FFMPEG_PATH = os.path.join(BASE_DIR, 'ffmpeg')
        if not os.path.exists(FFMPEG_PATH):
            FFMPEG_PATH = "ffmpeg"
    else:
        FFMPEG_PATH = "ffmpeg"
else:
    FFMPEG_PATH = "ffmpeg"

# ImageMagick is no longer used (replaced by Pillow)
IMAGEMAGICK_PATH = "magick"  # Kept for backward compatibility but not used

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

# Create directories if they don't exist
for directory in [VISION_DIR, AUDIO_DIR, OUTPUTS_DIR, DATA_DIR]:
    os.makedirs(directory, exist_ok=True)
