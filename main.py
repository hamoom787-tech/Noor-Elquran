"""
Quran Reels Video Generator - Backend Server
Flask server for generating short Reels videos of Quran verses
"""

import re
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import requests
import json
import os
import subprocess
import random
import time
from pathlib import Path
import shutil
import math
import difflib

import config
import youtube_seo
import webbrowser
import sys
import threading

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def is_safe_child_path(base_dir, candidate_path):
    """Return True when candidate_path resolves inside base_dir."""
    try:
        base_abs = os.path.abspath(base_dir)
        candidate_abs = os.path.abspath(candidate_path)
        return os.path.commonpath([base_abs, candidate_abs]) == base_abs
    except (OSError, ValueError):
        return False

app = Flask(__name__)
CORS(app)

# Global variable to track generation progress
generation_progress = {
    'status': 'idle',
    'progress': 0,
    'message': '',
    'video_path': None,
    'seo_status': 'idle',
    'seo_message': '',
    'seo_file': None,
    'seo_text_file': None,
    'seo_data': None
}

# Global Whisper model cache
whisper_model = None
generation_lock = threading.Lock()

SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')
SUPPORTED_BACKGROUND_AUDIO_EXTENSIONS = (
    '.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.mp4', '.webm'
)
SUPPORTED_LIBRARY_EXTENSIONS = SUPPORTED_VIDEO_EXTENSIONS + ('.ts',)
ALLOWED_VIDEO_FORMATS = {'portrait', 'landscape', 'square'}
PLATFORM_PRESETS = {
    'youtube_shorts': {
        'label': 'YouTube Shorts',
        'video_format': 'portrait',
        'width': 1080,
        'height': 1920,
        'overlay_offset_x': 0,
        'overlay_offset_y': -90,
    },
    'instagram_reels': {
        'label': 'Instagram Reels',
        'video_format': 'portrait',
        'width': 1080,
        'height': 1920,
        'overlay_offset_x': 0,
        'overlay_offset_y': -120,
    },
    'tiktok': {
        'label': 'TikTok',
        'video_format': 'portrait',
        'width': 1080,
        'height': 1920,
        'overlay_offset_x': -70,
        'overlay_offset_y': -130,
    },
    'youtube_landscape': {
        'label': 'YouTube Landscape',
        'video_format': 'landscape',
        'width': 1920,
        'height': 1080,
        'overlay_offset_x': 0,
        'overlay_offset_y': -40,
    },
    'square': {
        'label': 'Square',
        'video_format': 'square',
        'width': 1080,
        'height': 1080,
        'overlay_offset_x': 0,
        'overlay_offset_y': 0,
    },
}
LEGACY_PLATFORM_PRESETS = {
    'portrait': 'youtube_shorts',
    'landscape': 'youtube_landscape',
    'square': 'square',
}


def json_error(message, status_code=400):
    return jsonify({'success': False, 'error': message}), status_code


def json_success(data=None, **extra):
    payload = {'success': True}
    if data is not None:
        payload['data'] = data
    payload.update(extra)
    return jsonify(payload)


def get_safe_named_file(base_dir, filename):
    """Return an existing file inside base_dir, using only the basename from user input."""
    if not filename:
        return None

    safe_name = os.path.basename(str(filename))
    file_path = os.path.normpath(os.path.join(base_dir, safe_name))
    if is_safe_child_path(base_dir, file_path) and os.path.isfile(file_path):
        return file_path
    return None


def list_media_files(directory, extensions, include_duration=False):
    if not os.path.exists(directory):
        return []

    files = []
    for filename in os.listdir(directory):
        if not filename.lower().endswith(extensions):
            continue

        file_path = os.path.join(directory, filename)
        if not os.path.isfile(file_path):
            continue

        item = {
            'name': filename,
            'path': file_path,
            'size': os.path.getsize(file_path)
        }
        if include_duration:
            item['duration'] = round(get_audio_duration(file_path), 1)
        files.append(item)
    return files


def parse_generation_request(data):
    reciters = data.get('reciter_subfolder')
    if not reciters:
        raise ValueError('No reciter selected')

    if isinstance(reciters, str):
        reciters = [reciters]
    elif not isinstance(reciters, list):
        raise ValueError('Invalid reciter selection')

    try:
        surah_number = int(data.get('surah_number'))
        verse_from = int(data.get('verse_from'))
        verse_to = int(data.get('verse_to'))
        bg_audio_volume = float(data.get('bg_audio_volume', 0.15))
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid generation parameters') from exc

    if surah_number < 1 or verse_from < 1 or verse_to < verse_from:
        raise ValueError('Invalid verse range')

    platform_preset = data.get('platform_preset')
    video_format = data.get('video_format', 'portrait')

    if platform_preset not in PLATFORM_PRESETS:
        if video_format in LEGACY_PLATFORM_PRESETS:
            platform_preset = LEGACY_PLATFORM_PRESETS[video_format]
        else:
            platform_preset = 'youtube_shorts'

    video_format = PLATFORM_PRESETS[platform_preset]['video_format']

    bg_audio = get_safe_named_file(config.BACKGROUND_AUDIO_DIR, data.get('background_audio'))

    custom_bgs = data.get('custom_backgrounds')
    if isinstance(custom_bgs, str):
        custom_bgs = [custom_bgs]
    if custom_bgs:
        custom_bgs = [
            path for path in (
                get_safe_named_file(config.VISION_DIR, bg)
                for bg in custom_bgs
            )
            if path
        ] or None
    else:
        custom_bgs = None

    return {
        'reciters': reciters,
        'surah_number': surah_number,
        'verse_from': verse_from,
        'verse_to': verse_to,
        'video_format': video_format,
        'platform_preset': platform_preset,
        'custom_bgs': custom_bgs,
        'bg_audio': bg_audio,
        'bg_audio_volume': bg_audio_volume,
    }


# --- Data Fetching Functions ---

def fetch_reciters_list():
    """Return the specific list of requested reciters"""
    # Define the custom list directly
    reciters = [
        {'id': 'abdulbasit_murattal', 'name': 'عبد الباسط عبد الصمد (مرتل)', 'subfolder': 'Abdul_Basit_Murattal_192kbps'},
        {'id': 'husary', 'name': 'محمود خليل الحصري', 'subfolder': 'Husary_64kbps'},
        {'id': 'Minshawy_Murattal', 'name': 'محمد صديق المنشاوي (مرتل)', 'subfolder': 'Minshawy_Murattal_128kbps'},
        {'id': 'fares_abbad', 'name': 'فارس عباد', 'subfolder': 'Fares_Abbad_64kbps'},
        {'id': 'yasser_dosari', 'name': 'ياسر الدوسري', 'subfolder': 'Yasser_Ad-Dussary_128kbps'},
        {'id': 'maher', 'name': 'ماهر المعيقلي', 'subfolder': 'MaherAlMuaiqly128kbps'},
        {'id': 'banna', 'name': 'محمود علي البنا', 'subfolder': 'MAHMOUD_ALI_AL_BANNA_32kbps'},
        {'id': 'hudhaify', 'name': 'علي عبد الله هديفي', 'subfolder': 'Hudhaify_128kbps'},
        {'id': 'ali_jaber', 'name': 'علي جابر', 'subfolder': 'Ali_Jaber_64kbps'},
        {'id': 'ahmed_ibn_ali_al_ajamy', 'name': 'احمد ابن علي العجمي', 'subfolder': 'ahmed_ibn_ali_al_ajamy_128kbps'},
        {'id': 'abu_bakr_ash_shaatree', 'name': 'ابو بكر الشاطري', 'subfolder': 'Abu_Bakr_Ash-Shaatree_128kbps'},
        {'id': 'sahih_intnl_ibrahim_walk', 'name': 'إنجليزي/صحيح الدولي إبراهيم ووك', 'subfolder': 'English/Sahih_Intnl_Ibrahim_Walk_192kbps'},
    ]
    
    # Map of known incorrect reciter names to correct ones (for everyayah API)
    reciter_name_fixes = {}
    
    # Add preview URL to each reciter
    for reciter in reciters:
        # Resolve correct path for API
        path_name = reciter_name_fixes.get(reciter['subfolder'], reciter['subfolder'])
        
        # Determine likely correct URL (EveryAyah usually uses specific bitrate folder names)
        # Note: Some might fail if the folder name isn't exactly what EveryAyah expects,
        # but the list above seems mostly aligned with EveryAyah directory listing.
        
        # Special handling for subfolders with slashes
        clean_path = path_name.replace('\\', '/')
            
        reciter['preview_url'] = f"https://everyayah.com/data/{clean_path}/001002.mp3"
    
    # Save to cache just in case, though we use static return
    try:
        cache_file = os.path.join(config.DATA_DIR, 'reciters.json')
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(reciters, f, ensure_ascii=False, indent=2)
    except:
        pass
        
    return reciters


def get_reciter_display_name(subfolder):
    """Resolve reciter display name from subfolder."""
    for reciter in fetch_reciters_list():
        if reciter.get('subfolder') == subfolder:
            return reciter.get('name', subfolder)
    return subfolder

def fetch_surahs_list():
    cache_file = os.path.join(config.DATA_DIR, 'surahs.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    try:
        response = requests.get(f"{config.ALQURAN_API_BASE_URL}/surah", timeout=10)
        response.raise_for_status()
        data = response.json()
        surahs = []
        if data['code'] == 200:
            for surah in data['data']:
                surahs.append({
                    'number': surah['number'],
                    'name': surah['name'],
                    'englishName': surah['englishName'],
                    'numberOfAyahs': surah['numberOfAyahs']
                })
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(surahs, f, ensure_ascii=False, indent=2)
        return surahs
    except Exception as e:
        print(f"Error fetching surahs: {e}")
        return []



def fetch_verse_text(surah_number, verse_number):
    """Fetch Uthmani Quran text AND English Translation (with caching)"""
    cache_file = os.path.join(config.DATA_DIR, f'verse_{surah_number}_{verse_number}.json')
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    try:
        # Request both quran-uthmani and en.sahih (Sahih International)
        url = f"{config.ALQURAN_API_BASE_URL}/ayah/{surah_number}:{verse_number}/editions/quran-uthmani,en.sahih"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        result = {'arabic': '', 'english': ''}
        
        if data['code'] == 200:
            # The API returns a list of editions
            for edition in data['data']:
                text = edition['text']
                if edition['edition']['identifier'] == 'quran-uthmani':
                    # Remove Bismillah if it's NOT Surah Al-Fatiha (1) AND it's the 1st verse
                    basmala = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
                    if int(surah_number) != 1 and int(verse_number) == 1:
                        if text.startswith(basmala):
                            text = text[len(basmala):].strip()
                    result['arabic'] = text
                elif edition['edition']['identifier'] == 'en.sahih':
                    result['english'] = text
            
            # Cache the result
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False)
            except Exception as e:
                print(f"Error saving verse cache: {e}")

            return result
        return None
    except Exception as e:
        print(f"Error fetching verse text: {e}")
        return None





def download_audio_file(reciter_subfolder, surah_number, verse_number):
    """
    Downloads audio file with verification and retry logic.
    """
    max_retries = 3
    
    # Map of known incorrect reciter names to correct ones
    reciter_name_fixes = {}
    
    # Apply name fix if needed
    corrected_reciter = reciter_name_fixes.get(reciter_subfolder, reciter_subfolder)
    
    # Construct paths - handle subfolders with slashes (like English/Sahih_Intnl_Ibrahim_Walk_192kbps)
    # Replace backslashes and normalize path
    reciter_path = corrected_reciter.replace('\\', '/')
    audio_url = f"https://everyayah.com/data/{reciter_path}/{surah_number:03d}{verse_number:03d}.mp3"
    
    # Create safe filename (replace slashes with underscores)
    safe_reciter_name = reciter_subfolder.replace('/', '_').replace('\\', '_')
    audio_filename = f"{safe_reciter_name}_v2_{surah_number:03d}{verse_number:03d}.mp3"
    audio_path = os.path.join(config.AUDIO_DIR, audio_filename)
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Check if file exists and is valid size (e.g. > 2KB)
            if os.path.exists(audio_path):
                file_size = os.path.getsize(audio_path)
                if file_size > 2000:
                   return audio_path
                else:
                   print(f"File exists but too small ({file_size} bytes). Re-downloading...")
                   try:
                       os.remove(audio_path)
                   except:
                       pass
            
            print(f"Downloading audio: {audio_url} (Attempt {attempt+1}/{max_retries})")
            # Ensure folder exists
            os.makedirs(os.path.dirname(audio_path), exist_ok=True)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'audio/mpeg, audio/*, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://everyayah.com/'
            }
            
            response = requests.get(audio_url, headers=headers, timeout=60, stream=True)
            
            if response.status_code == 404:
                # Try alternative reciter name formats if first attempt failed
                if attempt == 0:
                    # Try removing bitrate suffix (e.g., _48kbps, _128kbps)
                    if '_' in corrected_reciter and any(x in corrected_reciter for x in ['_48kbps', '_128kbps', '_64kbps', '_192kbps', '_32kbps']):
                        alt_reciter = corrected_reciter
                        for suffix in ['_48kbps', '_128kbps', '_64kbps', '_192kbps', '_32kbps']:
                            alt_reciter = alt_reciter.replace(suffix, '')
                        
                        alt_url = f"https://everyayah.com/data/{alt_reciter}/{surah_number:03d}{verse_number:03d}.mp3"
                        print(f"Trying alternative URL (without bitrate): {alt_url}")
                        alt_response = requests.get(alt_url, headers=headers, timeout=60, stream=True)
                        if alt_response.status_code == 200:
                            # Use the alternative URL
                            audio_url = alt_url
                            reciter_path = alt_reciter
                            response = alt_response
                            print(f"Success with alternative URL! Using: {alt_reciter}")
                            # Continue with the successful response
                        else:
                            last_error = f"File not found (404) - Tried both '{reciter_path}' and '{alt_reciter}'"
                            print(f"HTTP 404: Audio file not found at {audio_url} or {alt_url}")
                            print(f"Possible reasons: Reciter '{reciter_subfolder}' may not have verse {surah_number}:{verse_number}")
                            break
                    else:
                        last_error = f"File not found (404) - The audio file may not exist for this reciter/verse combination"
                        print(f"HTTP 404: Audio file not found at {audio_url}")
                        print(f"Possible reasons: Reciter '{reciter_subfolder}' may not have verse {surah_number}:{verse_number}")
                        break
                else:
                    # Already tried alternatives, give up
                    break
            elif response.status_code != 200:
                last_error = f"HTTP Error {response.status_code}"
                print(f"HTTP Error {response.status_code} for {audio_url}")
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))  # Exponential backoff
                continue
            
            # Verify Content Length if available
            content_length = int(response.headers.get('content-length', 0))
            if content_length > 0 and content_length < 2000:
                 print(f"Warning: Remote file is very small ({content_length} bytes). Might be invalid.")
            
            # Download with streaming for large files
            total_size = 0
            with open(audio_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
                
            # Final verify of written file
            if not os.path.exists(audio_path):
                last_error = "File was not created after download"
                print("Downloaded file does not exist. Retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                continue
                
            file_size = os.path.getsize(audio_path)
            if file_size < 2000:
                 last_error = f"Downloaded file is too small ({file_size} bytes)"
                 print(f"Downloaded file is too small ({file_size} bytes). Retrying...")
                 try:
                     os.remove(audio_path)
                 except:
                     pass
                 if attempt < max_retries - 1:
                     time.sleep(1)
                 continue
                 
            print(f"Successfully downloaded audio: {file_size} bytes")
            return audio_path

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            print(f"Timeout downloading audio (Attempt {attempt+1}): {audio_url}")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {str(e)}"
            print(f"Connection error (Attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
        except Exception as e:
            last_error = f"Error: {str(e)}"
            print(f"Error downloading audio (Attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            
    # If we get here, all retries failed
    error_msg = f"Failed to download audio after {max_retries} attempts for Verse {surah_number}:{verse_number}"
    if last_error:
        error_msg += f"\nLast error: {last_error}"
    error_msg += f"\nURL: {audio_url}"
    error_msg += f"\nReciter: {reciter_subfolder}"
    raise Exception(error_msg)

def get_audio_duration(audio_path):
    try:
        cmd = [config.FFMPEG_PATH, '-i', audio_path, '-hide_banner']
        # Redirect stderr to stdout to capture duration
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore')
        
        output = result.stdout
        if output:
            for line in output.split('\n'):
                if 'Duration:' in line:
                    try:
                        time_str = line.split('Duration:')[1].split(',')[0].strip()
                        h, m, s = time_str.split(':')
                        duration = int(h) * 3600 + int(m) * 60 + float(s)
                        return duration
                    except:
                        continue
        return 0
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0

# --- Smart Alignment Helpers ---

def normalize_arabic(text):
    """
    Normalize Arabic text for comparison (remove tashkeel, unify alefs/taa).
    """
    # Remove Tashkeel (Diacritics)
    tashkeel = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED]')
    text = re.sub(tashkeel, '', text)
    
    # Unify Alefs
    text = re.sub(r'[إأآٱ]', 'ا', text)
    
    # Unify Taa Marbuta / Ha
    text = re.sub(r'ة', 'ه', text)
    
    # Unify Ya / Alif Maqsura
    text = re.sub(r'ى', 'ي', text)
    
    return text.strip()

def analyze_audio_with_whisper(audio_path, target_words_list):
    """
    Advanced Sequence Alignment between Uthmani Script and Whisper Output.
    """
    global whisper_model
    try:
        if not getattr(config, "WHISPER_ENABLED", True):
            print("Whisper is disabled. Using fallback timing.")
            return fallback_timing(audio_path, target_words_list)

        if whisper_model is None:
            import whisper

            model_name = getattr(config, "WHISPER_MODEL", "base")
            print(f"Loading Whisper model ({model_name})...")
            whisper_model = whisper.load_model(model_name)
        
        # 1. Transcribe
        print(f"Transcribing {audio_path}...")
        result = whisper_model.transcribe(audio_path, word_timestamps=True)
        
        recognized_words = []
        for segment in result.get('segments', []):
            for word in segment.get('words', []):
                recognized_words.append({
                    'word': word['word'].strip(),
                    'norm': normalize_arabic(word['word'].strip()),
                    'start': word['start'],
                    'end': word['end']
                })
                
        # 2. Prepare Inputs
        # Target (Uthmani) -> Normalized List
        target_norm = [normalize_arabic(w) for w in target_words_list]
        
        # Source (Whisper) -> Normalized List
        source_norm = [w['norm'] for w in recognized_words]
        
        # 3. Fuzzy Alignment using SequenceMatcher
        matcher = difflib.SequenceMatcher(None, target_norm, source_norm)
        
        final_timings = [None] * len(target_words_list)
        matches = []
        
        # Extract Anchors (Exact or reliable matches)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Direct match found
                for k in range(i2 - i1):
                    target_idx = i1 + k
                    source_idx = j1 + k
                    
                    final_timings[target_idx] = {
                        'word': target_words_list[target_idx],
                        'start': recognized_words[source_idx]['start'],
                        'end': recognized_words[source_idx]['end']
                    }
                    matches.append(target_idx)
            
            elif tag == 'replace':
                # Fuzzy Check: Are they close enough?
                # e.g. "rhman" vs "rahman"
                for k in range(min(i2-i1, j2-j1)):
                    target_idx = i1 + k
                    source_idx = j1 + k
                    t_word = target_norm[target_idx]
                    s_word = source_norm[source_idx]
                    
                    # High similarity threshold
                    if difflib.SequenceMatcher(None, t_word, s_word).ratio() > 0.7:
                        final_timings[target_idx] = {
                            'word': target_words_list[target_idx],
                            'start': recognized_words[source_idx]['start'],
                            'end': recognized_words[source_idx]['end']
                        }
                        matches.append(target_idx)

        # 4. Interpolate Gaps (The "Smart" Filling)
        # We accept that we have Audio Duration available
        duration = get_audio_duration(audio_path)
        
        # Add virtual anchors at start and end if missing
        start_anchor = 0.0
        end_anchor = duration
        
        current_start = start_anchor
        last_match_idx = -1
        
        for i in range(len(final_timings)):
            if final_timings[i] is not None:
                # We have a known timing (Anchor)
                anchor = final_timings[i]
                
                # Fill gap between last_match_idx and this anchor i
                gap_start = current_start
                gap_end = anchor['start']
                gap_duration = max(0, gap_end - gap_start)
                
                # Number of missing words in between
                missing_count = i - last_match_idx - 1
                
                if missing_count > 0:
                    # Distribute gap proportionally based on word length
                    # (Longer words get more time)
                    missing_words = target_words_list[last_match_idx+1 : i]
                    total_chars = sum(len(w) for w in missing_words) or 1
                    
                    current_gap_time = gap_start
                    
                    for j, missing_word in enumerate(missing_words):
                        # Calculate duration for this word
                        weight = len(missing_word) / total_chars
                        w_dur = gap_duration * weight
                        
                        w_idx = last_match_idx + 1 + j
                        final_timings[w_idx] = {
                            'word': missing_word,
                            'start': current_gap_time,
                            'end': current_gap_time + w_dur
                        }
                        current_gap_time += w_dur
                
                # Update pointers
                current_start = anchor['end']
                last_match_idx = i
                
        # 5. Fill Tail (after last anchor)
        remaining_words_count = len(final_timings) - 1 - last_match_idx
        if remaining_words_count > 0:
            gap_start = current_start
            gap_end = end_anchor
            gap_duration = max(0, gap_end - gap_start)
            
            missing_words = target_words_list[last_match_idx+1 : ]
            total_chars = sum(len(w) for w in missing_words) or 1
            
            current_gap_time = gap_start
            for j, missing_word in enumerate(missing_words):
                weight = len(missing_word) / total_chars
                w_dur = gap_duration * weight
                w_idx = last_match_idx + 1 + j
                final_timings[w_idx] = {
                    'word': missing_word,
                    'start': current_gap_time,
                    'end': current_gap_time + w_dur
                }
                current_gap_time += w_dur

        return final_timings

    except Exception as e:
        print(f"Smart Align Error: {e}. Falling back...")
        return fallback_timing(audio_path, target_words_list)


def fallback_timing(audio_path, words_list):
    """Original fallback method using simple duration division"""
    duration = get_audio_duration(audio_path)
    num_words = len(words_list)
    if num_words == 0: return []
    
    avg_dur = duration / num_words
    return [{'word': w, 'start': i*avg_dur, 'end': (i+1)*avg_dur} for i, w in enumerate(words_list)]

# Renaming original analyze function to keep as reference or delete?
# The user wants "Perfect", so we replace the logic.


def merge_audio_files(audio_files, output_path):
    try:
        if len(audio_files) == 1:
            shutil.copy(audio_files[0], output_path)
            return output_path
        
        list_file = os.path.join(config.AUDIO_DIR, 'concat_list.txt')
        with open(list_file, 'w', encoding='utf-8') as f:
            for audio_file in audio_files:
                audio_file_path = audio_file.replace('\\', '/')
                f.write(f"file '{audio_file_path}'\n")
        
        cmd = [
            config.FFMPEG_PATH, '-f', 'concat', '-safe', '0',
            '-i', list_file, '-c', 'copy', '-y', output_path
        ]
        # Use DEVNULL to avoid buffer filling
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        os.remove(list_file)
        return output_path
    except Exception as e:
        print(f"Error merging audio: {e}")
        return None

# --- Text Processing Functions ---

def split_text_into_chunks(text_obj, max_words=5, word_timings=None):
    """
    Split both Arabic and English texts into synchronized chunks with real timing.
    text_obj: {'arabic': '...', 'english': '...'}
    word_timings: List of dicts with 'word', 'start', 'end' keys (from analyze_audio_timing)
    Returns: List of chunks with 'arabic', 'english', 'start', 'end' keys
    """
    if not text_obj or not text_obj.get('arabic'):
        return []

    arabic_words = text_obj['arabic'].split()
    english_words = text_obj.get('english', '').split()
    
    chunks = []
    
    # If we have word timings, use them for accurate synchronization
    if word_timings and len(word_timings) > 0:
        # Group words into chunks based on max_words, using actual timings
        current_chunk_words_ar = []
        current_chunk_words_en = []
        current_chunk_start = None
        current_chunk_end = None
        word_idx = 0
        
        for i, word in enumerate(arabic_words):
            if word_idx < len(word_timings):
                word_timing = word_timings[word_idx]
                word_start = word_timing['start']
                word_end = word_timing['end']
                
                # Initialize chunk start time
                if current_chunk_start is None:
                    current_chunk_start = word_start
                
                current_chunk_words_ar.append(word)
                current_chunk_end = word_end
                word_idx += 1
                
                # If we've reached max_words or this is the last word, finalize chunk
                if len(current_chunk_words_ar) >= max_words or i == len(arabic_words) - 1:
                    # Calculate English words for this chunk proportionally
                    if len(english_words) > 0:
                        # Map Arabic chunk to English proportionally
                        ar_start_idx = i - len(current_chunk_words_ar) + 1
                        ar_end_idx = i + 1
                        ar_proportion = (ar_end_idx - ar_start_idx) / len(arabic_words)
                        
                        en_start_idx = int(len(english_words) * (ar_start_idx / len(arabic_words)))
                        en_end_idx = int(len(english_words) * (ar_end_idx / len(arabic_words)))
                        en_chunk = " ".join(english_words[en_start_idx:en_end_idx])
                    else:
                        en_chunk = ""
                    
                    chunks.append({
                        'arabic': " ".join(current_chunk_words_ar),
                        'english': en_chunk,
                        'start': current_chunk_start,
                        'end': current_chunk_end
                    })
                    
                    # Reset for next chunk
                    current_chunk_words_ar = []
                    current_chunk_words_en = []
                    current_chunk_start = None
                    current_chunk_end = None
        
        # Handle remaining words if any (shouldn't happen, but just in case)
        if current_chunk_words_ar:
            if len(english_words) > 0:
                ar_start_idx = len(arabic_words) - len(current_chunk_words_ar)
                ar_end_idx = len(arabic_words)
                en_start_idx = int(len(english_words) * (ar_start_idx / len(arabic_words)))
                en_end_idx = len(english_words)
                en_chunk = " ".join(english_words[en_start_idx:en_end_idx])
            else:
                en_chunk = ""
            
            # Use last known end time or estimate
            final_end = current_chunk_end if current_chunk_end else (word_timings[-1]['end'] if word_timings else 0)
            chunks.append({
                'arabic': " ".join(current_chunk_words_ar),
                'english': en_chunk,
                'start': current_chunk_start if current_chunk_start else 0,
                'end': final_end
            })
    else:
        # Fallback: Original method without timings (for backward compatibility)
        num_chunks = math.ceil(len(arabic_words) / max_words)
        if num_chunks == 0: num_chunks = 1
        
        english_chunk_size = math.ceil(len(english_words) / num_chunks)
        
        for i in range(num_chunks):
            start_ar = i * max_words
            end_ar = start_ar + max_words
            ar_chunk = " ".join(arabic_words[start_ar:end_ar])
            
            start_en = i * english_chunk_size
            end_en = start_en + english_chunk_size
            en_chunk = " ".join(english_words[start_en:end_en])
            
            chunks.append({
                'arabic': ar_chunk,
                'english': en_chunk
            })
    
    return chunks

def generate_pango_markup(text):
    """
    Wraps Arabic diacritics in Pango markup spans to color them gold.
    """
    # Unicode range for Arabic Diacritics (Harakat)
    # 064B-0652: Fathatan, Dammatan, Kasratan, Fatha, Damma, Kasra, Shadda, Sukun
    # 0670: Superscript Aleph
    # 0653-065F: Other marks
    diacritics_pattern = r'([\u064B-\u065F\u0670])'
    
    # Escape XML characters just in case
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Replace diacritics with colored span
    # We color the diacritic GOLD
    colored_text = re.sub(
        diacritics_pattern, 
        f'<span foreground="{config.TASHKEEL_COLOR}">\\1</span>', 
        text
    )
    
    return colored_text

def _load_font(size, preferred=None):
    from PIL import ImageFont

    try:
        if preferred:
            return ImageFont.truetype(preferred, size)
    except Exception:
        pass

    font_candidates = [
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "C:/Windows/Fonts/trado.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for font_path in font_candidates:
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _wrap_text_to_width(draw, text, font, max_width):
    words = text.split()
    if not words:
        return []

    lines = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def create_text_chunk_image_with_pillow(chunk_data, width, height, output_path):
    try:
        from PIL import Image, ImageDraw, ImageFont

        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
        except Exception:
            arabic_reshaper = None
            get_display = None

        if isinstance(chunk_data, str):
            chunk_data = {'arabic': chunk_data, 'english': ''}

        arabic_text = chunk_data.get('arabic', '')
        english_text = chunk_data.get('english', '')
        if arabic_text:
            arabic_text = f"﴿ {arabic_text} ﴾"
            if arabic_reshaper and get_display:
                arabic_text = get_display(arabic_reshaper.reshape(arabic_text))

        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        arabic_font = _load_font(config.TEXT_FONT_SIZE, config.TEXT_FONT)
        english_font = _load_font(config.TRANSLATION_FONT_SIZE, "arial.ttf")
        max_text_width = width - 70

        arabic_lines = _wrap_text_to_width(draw, arabic_text, arabic_font, max_text_width)
        english_lines = _wrap_text_to_width(draw, english_text, english_font, int(width * 0.75))
        spacing = 12
        line_metrics = []

        for line in arabic_lines:
            bbox = draw.textbbox((0, 0), line, font=arabic_font)
            line_metrics.append((line, arabic_font, config.TEXT_COLOR, bbox[3] - bbox[1]))
        if arabic_lines and english_lines:
            line_metrics.append(("", english_font, "white", spacing))
        for line in english_lines:
            bbox = draw.textbbox((0, 0), line, font=english_font)
            line_metrics.append((line, english_font, "white", bbox[3] - bbox[1]))

        total_height = sum(item[3] for item in line_metrics) + spacing * max(0, len(line_metrics) - 1)
        y = max(20, (height - total_height) // 2)
        shadow_offset = 3

        for line, font, fill, line_height in line_metrics:
            if not line:
                y += line_height
                continue
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = max(10, (width - text_width) // 2)
            draw.text((x + shadow_offset, y + shadow_offset), line, font=font, fill=(0, 0, 0, 210))
            draw.text((x, y), line, font=font, fill=fill)
            y += line_height + spacing

        image.save(output_path, 'PNG')
        return True
    except Exception as e:
        print(f"Pillow text fallback failed: {e}")
        return False

def create_text_chunk_image(chunk_data, width, height, output_path):
    """
    Create text image with Arabic (Gold Diacritics) AND English Translation.
    chunk_data: {'arabic': '...', 'english': '...'} or just string (legacy support)
    """
    try:
        # Handle legacy string input if any
        if isinstance(chunk_data, str):
            chunk_data = {'arabic': chunk_data, 'english': ''}
            
        arabic_text = chunk_data.get('arabic', '')
        english_text = chunk_data.get('english', '')
        
        # Prepare Markups
        markup = generate_pango_markup(arabic_text)

        # Add Ornate Brackets
        bracket_start = f"<span foreground='{config.TASHKEEL_COLOR}'>﴿</span>"
        bracket_end = f"<span foreground='{config.TASHKEEL_COLOR}'>﴾</span>"
        markup = f"{bracket_start} {markup} {bracket_end}"
        
        # Pango for Arabic
        pango_arabic = (
            f"<span font='{config.TEXT_FONT} {config.TEXT_FONT_SIZE}' foreground='{config.TEXT_COLOR}'>"
            f"{markup}"
            f"</span>"
        )
        
        # Pango for English
        english_safe = english_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        pango_english = (
            f"<span font='Arial {config.TRANSLATION_FONT_SIZE}' foreground='white'>"
            f"{english_safe}"
            f"</span>"
        )
        
        # Calculate safe widths
        # Arabic gets full width minus padding
        arabic_width = width - 50
        # English gets 80% of screen width
        english_width = int(width * 0.6)
        
        # Command strategy: Render separately, then append
        cmd = [
            config.IMAGEMAGICK_PATH,
            '-background', 'transparent',
            '-gravity', 'Center',
        ]
        
        # 1. Render Arabic
        cmd.extend(['(', '-size', f'{arabic_width}x', f'pango:{pango_arabic}', ')'])
        
        # 2. Render English (if exists) and append
        if english_safe.strip():
             # Add a bit of spacing before English (transparent spacer not easily done with just append, 
             # but we can rely on Pango or just let append handle it. 
             # To add space, we could append a transparent spacer, but let's keep it simple first)
             cmd.extend(['(', '-size', f'{english_width}x', f'pango:{pango_english}', ')'])
             cmd.extend(['-append'])
             
        # 3. Apply effects and extent
        cmd.extend([
            # --- Add Blur/Shadow Effect ---
            '(', '+clone', '-background', 'black', '-shadow', '80x3+0+0', ')', 
            '+swap', '-background', 'none', '-layers', 'merge', '+repage',
            # ------------------------------
            
            '-gravity', 'Center',          # Important: Center the previous image on the new canvas
            '-extent', f'{width}x{height}',# Extend to full size
            output_path
        ])
        
        # Run ImageMagick
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(output_path):
            return True
        else:
            print(f"ImageMagick Pango failed: {result.stderr}. Falling back to standard method.")
            raise Exception("ImageMagick failed")

    except Exception as e:
        print(f"Fallback to PIL for text generation: {e}")
        return create_text_chunk_image_with_pillow(chunk_data, width, height, output_path)

# --- Video Generation ---

def render_verse_segment(background_video, audio_path, overlay_configs, total_duration, output_segment_path, width, height, do_fade_in=False, do_fade_out=False, bg_start_time=0.0, overlay_offset_x=0, overlay_offset_y=0):
    """
    Renders a single verse segment into a .ts file (better for concatenation).
    """
    try:
        cmd = [config.FFMPEG_PATH]
        
        # Input 0: Background (Infinite loop, starting at specific offset)
        cmd.extend(['-stream_loop', '-1', '-ss', str(bg_start_time), '-i', background_video])
        
        # Input 1: Audio
        cmd.extend(['-i', audio_path])
        
        # Input 2..N: Text Images
        for overlay in overlay_configs:
            # For segments, we loop the image for the duration of the segment
            cmd.extend(['-loop', '1', '-t', str(total_duration + 1), '-i', overlay['path']])
            
        filter_complex = []
        
        # Prepare Background (Scale & Crop)
        bg_filter = f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}[bg0];"
        filter_complex.append(bg_filter)
        
        last_bg_label = "bg0"
        for i, overlay in enumerate(overlay_configs):
            input_idx = i + 2
            text_label = f"txt{i}"
            next_bg_label = f"bg{i+1}"
            
            start = overlay['start']
            end = overlay['end']
            duration = end - start
            fade_dur = min(0.3, duration / 3)
            
            # Apply Fade
            force_fade = f"[{input_idx}:v]format=rgba,fade=t=in:st={start}:d={fade_dur}:alpha=1,fade=t=out:st={end-fade_dur}:d={fade_dur}:alpha=1[{text_label}];"
            filter_complex.append(force_fade)
            
            # Overlay
            overlay_x = f"(W-w)/2{int(overlay_offset_x):+d}"
            overlay_y = f"(H-h)/2{int(overlay_offset_y):+d}"
            overlay_cmd = f"[{last_bg_label}][{text_label}]overlay={overlay_x}:{overlay_y}:enable='between(t,{start},{end})':shortest=1[{next_bg_label}];"
            filter_complex.append(overlay_cmd)
            last_bg_label = next_bg_label

        # Apply Global Fade In/Out if requested
        final_video_label = "v_faded"
        fade_filters = []
        if do_fade_in:
            fade_filters.append("fade=t=in:st=0:d=0.5")
        if do_fade_out:
            # Fade out at the end
            fade_filters.append(f"fade=t=out:st={total_duration-0.5}:d=0.5")
        
        if fade_filters:
            fade_string = ",".join(fade_filters)
            filter_complex.append(f"[{last_bg_label}]{fade_string}[{final_video_label}]")
        else:
            final_video_label = last_bg_label
            # Ensure the chain ends properly if no fades
            if filter_complex:
                 filter_complex[-1] = filter_complex[-1].replace(f"[{last_bg_label}];", f"[{final_video_label}]")
            else:
                 filter_complex.append(f"[{last_bg_label}]null[{final_video_label}]")


        # Clean up the logic for filter_complex string generation
        # The previous loop might leave a trailing semicolon or not connect to [v]
        # Let's reconstruct the final mapping
        
        full_filter = "".join(filter_complex)
        
        # Remove trailing semicolon if exists before appending the map
        if full_filter.endswith(';'):
            full_filter = full_filter[:-1]

        cmd.extend(['-filter_complex', full_filter])
        # Map the final video label
        cmd.extend(['-map', f'[{final_video_label}]', '-map', '1:a'])
        
        # Output as MPEG-TS (highly robust for concat)
        cmd.extend(['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28'])
        cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
        cmd.extend(['-t', str(total_duration)])
        cmd.extend(['-y', output_segment_path])
        
        # Run with DEVNULL for speed/memory
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception as e:
        print(f"Error rendering segment: {e}")
        return False

# --- Video Generation ---

def generate_video(reciter_subfolders, surah_number, verse_from, verse_to, video_format='portrait', custom_backgrounds=None, background_audio=None, bg_audio_volume=0.15, platform_preset=None):
    """
    reciter_subfolders: List of strings (single reciter)
    video_format: legacy format key. platform_preset controls final dimensions when present.
    custom_backgrounds: List of absolute paths to background videos (Manual Mode)
    """
    global generation_progress
    
    if platform_preset not in PLATFORM_PRESETS:
        platform_preset = LEGACY_PLATFORM_PRESETS.get(video_format, 'youtube_shorts')

    preset = PLATFORM_PRESETS[platform_preset]
    video_format = preset['video_format']
    width = preset['width']
    height = preset['height']
    overlay_offset_x = preset.get('overlay_offset_x', 0)
    overlay_offset_y = preset.get('overlay_offset_y', 0)
    
    # Ensure reciter_subfolders is a list
    if isinstance(reciter_subfolders, str):
        reciter_subfolders = [reciter_subfolders]
    
    segments_dir = os.path.join(config.DATA_DIR, f"temp_segments_{int(time.time())}")
    os.makedirs(segments_dir, exist_ok=True)
    
    try:
        generation_progress['status'] = 'running'
        generation_progress['progress'] = 5
        generation_progress['message'] = 'تحليل البيانات وتجهيز الملفات...'
        generation_progress['seo_status'] = 'idle'
        generation_progress['seo_message'] = ''
        generation_progress['seo_file'] = None
        generation_progress['seo_text_file'] = None
        generation_progress['seo_data'] = None
        
        verse_count = verse_to - verse_from + 1
        selected_project_bgs = []
        verse_contexts = []

        # 1. Prepare Background Selection
        if custom_backgrounds and len(custom_backgrounds) > 0:
            # --- Manual Mode ---
            print(f"Using manual backgrounds: {len(custom_backgrounds)} selected")
            if len(custom_backgrounds) != verse_count:
                # Fallback or Error? Ideally the UI prevents this. 
                # If mismatch, we loop or trim.
                print("Warning: Custom backgrounds count mismatch. Adjusting...")
            
            # Ensure we have enough by cycling if needed
            for k in range(verse_count):
                selected_project_bgs.append(custom_backgrounds[k % len(custom_backgrounds)])
                
        else:
            # --- Random Mode (Original Logic) ---
            background_videos = []
            for ext in ['*.mp4', '*.mov', '*.avi', '*.mkv']:
                background_videos.extend(list(Path(config.VISION_DIR).glob(ext)))
            
            # Sort to ensure consistent order before shuffle
            background_videos.sort()
            if not background_videos:
                raise Exception("No background videos found in vision/")
                
            # Persistent Background Logic
            used_bg_file = os.path.join(config.DATA_DIR, 'used_backgrounds.json')
            used_bgs = []
            if os.path.exists(used_bg_file):
                try:
                    with open(used_bg_file, 'r', encoding='utf-8') as f:
                        used_bgs = json.load(f)
                except:
                    used_bgs = []

            # Filter available backgrounds
            available_bgs = [str(bg) for bg in background_videos if str(bg) not in used_bgs]
            
            # If we ran out of new backgrounds, reset logic
            if len(available_bgs) < verse_count:
                print("Resetting used backgrounds list to ensure variety.")
                used_bgs = []
                available_bgs = [str(bg) for bg in background_videos]

            # Shuffle available backgrounds
            random.shuffle(available_bgs)
            
            # Select backgrounds for this project
            for k in range(verse_count):
                selected_project_bgs.append(available_bgs[k % len(available_bgs)])
                
            # Update used list
            for bg in selected_project_bgs:
                if bg not in used_bgs:
                    used_bgs.append(bg)
                    
            # Save updated used list
            with open(used_bg_file, 'w', encoding='utf-8') as f:
                json.dump(used_bgs, f, ensure_ascii=False, indent=2)
            
        # -----------------------------------
            
        # -----------------------------------
        
        verse_data = [] # List of config dicts
        total_verses = verse_to - verse_from + 1
        
        # Track time offsets for each background video for continuous playback
        bg_time_offsets = {}
        
        # 2. Loop Through Verses
        for i, verse_num in enumerate(range(verse_from, verse_to + 1)):
            progress = 5 + int((i / total_verses) * 20)
            generation_progress['progress'] = progress
            generation_progress['message'] = f'تجهيز الآية {verse_num}...'

            # Pick a unique background for THIS verse (cycle through list)
            background_video = selected_project_bgs[i]

            # Use the single selected reciter for all verses
            current_reciter = reciter_subfolders[0]

            try:
                audio_path = download_audio_file(current_reciter, surah_number, verse_num)
            except Exception as e:
                error_msg = str(e)
                generation_progress['status'] = 'error'
                generation_progress['message'] = f'خطأ في تحميل صوت الآية {verse_num}: {error_msg}'
                raise Exception(f'فشل تحميل صوت الآية {verse_num}. {error_msg}')
            
            duration = get_audio_duration(audio_path)
            if duration <= 0:
                raise Exception(f'مدة الصوت غير صحيحة للآية {verse_num}')
            text_obj = fetch_verse_text(surah_number, verse_num)
            if not text_obj: text_obj = {'arabic': "...", 'english': ""}
            verse_contexts.append({
                'verse_number': verse_num,
                'arabic': text_obj.get('arabic', ''),
                'english': text_obj.get('english', '')
            })
            
            # Analyze audio timing for real synchronization using Whisper
            arabic_words = text_obj['arabic'].split()
            generation_progress['message'] = f'جاري المزامنة بالذكاء الاصطناعي (Whisper)...'
            word_timings = analyze_audio_with_whisper(audio_path, arabic_words)

            
            # Split text into chunks with real timing
            chunks = split_text_into_chunks(text_obj, config.MAX_WORDS_PER_CHUNK, word_timings)
            
            # Create Images for this verse
            verse_overlay_configs = []
            
            for j, chunk_data in enumerate(chunks):
                img_path = os.path.join(segments_dir, f"v{verse_num}_c{j}.png")
                if create_text_chunk_image(chunk_data, width, height, img_path):
                    # Use real timing from chunk if available, otherwise fallback
                    if 'start' in chunk_data and 'end' in chunk_data:
                        chunk_start = chunk_data['start']
                        chunk_end = chunk_data['end']
                    else:
                        # Fallback: calculate proportionally
                        total_char_len = sum(len(c['arabic'].replace(' ', '')) for c in chunks) or 1
                        chunk_len = len(chunk_data['arabic'].replace(' ', '')) or 1
                        chunk_proportion = chunk_len / total_char_len
                        chunk_start = sum(c.get('start', 0) for c in chunks[:j]) if j > 0 else 0
                        chunk_end = chunk_start + (chunk_proportion * duration)
                    
                    verse_overlay_configs.append({
                        'path': img_path,
                        'start': chunk_start,
                        'end': chunk_end
                    })

            # Determine fades
            do_fade_in = (i == 0)
            do_fade_out = (i == total_verses - 1)

            # Calculate background offset
            bg_duration = get_audio_duration(background_video)
            current_bg_offset = bg_time_offsets.get(background_video, 0.0)
            if bg_duration > 0:
                safe_offset = current_bg_offset % bg_duration
            else:
                safe_offset = 0.0
            
            # Update offset for next use of this same background
            bg_time_offsets[background_video] = current_bg_offset + duration

            # 3. Render THIS verse segment immediately with its background
            segment_path = os.path.join(segments_dir, f"segment_{i:04d}.ts")
            # Log which reciter is being used for this verse
            print(f"Verse {verse_num} - Reciter: {current_reciter} - Preset: {platform_preset} - BG Offset: {safe_offset:.1f}s")
            generation_progress['message'] = f'توليد فيديو الآية {verse_num}...'
            if not render_verse_segment(
                background_video,
                audio_path,
                verse_overlay_configs,
                duration,
                segment_path,
                width,
                height,
                do_fade_in=do_fade_in,
                do_fade_out=do_fade_out,
                bg_start_time=safe_offset,
                overlay_offset_x=overlay_offset_x,
                overlay_offset_y=overlay_offset_y,
            ):
                raise Exception(f"فشل توليد مقطع الآية {verse_num}")
            
            verse_data.append(segment_path)
            # Update progress based on segments rendered
            generation_progress['progress'] = 25 + int((i / total_verses) * 50)

        # 4. Concatenate All Segments
        generation_progress['progress'] = 80
        generation_progress['message'] = 'دمج المقاطع النهائية...'
        
        concat_file = os.path.join(segments_dir, 'concat.txt')
        with open(concat_file, 'w') as f:
            for seg in verse_data:
                f.write(f"file '{os.path.abspath(seg).replace('\\', '/')}'\n")
        
        output_filename = f"quran_video_{platform_preset}_{int(time.time())}.mp4"
        output_path = os.path.join(config.OUTPUTS_DIR, output_filename)
        
        # If background audio is selected, we need to concat first then mix
        if background_audio:
            # Step 4a: Concat segments into a temp file first
            temp_concat_path = os.path.join(segments_dir, 'temp_concat.mp4')
            concat_cmd = [
                config.FFMPEG_PATH, '-f', 'concat', '-safe', '0',
                '-i', concat_file, '-c', 'copy', '-y', temp_concat_path
            ]
            subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            # Step 4b: Mix background audio with the concatenated video
            generation_progress['progress'] = 90
            generation_progress['message'] = 'دمج الصوت الخلفي...'
            
            # Resolve background audio path
            bg_audio_path = background_audio
            if not os.path.isabs(bg_audio_path):
                bg_audio_path = os.path.join(config.BACKGROUND_AUDIO_DIR, bg_audio_path)
            
            if os.path.exists(bg_audio_path):
                # Get video duration for trimming background audio
                video_duration = get_audio_duration(temp_concat_path)
                
                # Mix: recitation stays at full volume, background audio at custom volume
                # -stream_loop -1 loops the background audio if it's shorter than the video
                mix_cmd = [
                    config.FFMPEG_PATH,
                    '-i', temp_concat_path,
                    '-stream_loop', '-1', '-i', bg_audio_path,
                    '-filter_complex',
                    f'[1:a]volume={bg_audio_volume}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]',
                    '-map', '0:v', '-map', '[aout]',
                    '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '192k',
                    '-t', str(video_duration),
                    '-y', output_path
                ]
                subprocess.run(mix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                # Background audio file not found, just use the concat file
                print(f"Warning: Background audio file not found: {bg_audio_path}")
                shutil.copy(temp_concat_path, output_path)
        else:
            # No background audio, just concat normally
            concat_cmd = [
                config.FFMPEG_PATH, '-f', 'concat', '-safe', '0',
                '-i', concat_file, '-c', 'copy', '-y', output_path
            ]
            subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # 5. Generate YouTube SEO metadata (non-blocking for final success)
        if config.SEO_ENABLED:
            generation_progress['progress'] = 95
            generation_progress['seo_status'] = 'running'
            generation_progress['seo_message'] = 'تجهيز بيانات يوتيوب (SEO)...'

            surah_name_ar = ''
            surah_name_en = ''
            try:
                surah_lookup = next(
                    (s for s in fetch_surahs_list() if int(s.get('number', 0)) == int(surah_number)),
                    None
                )
                if surah_lookup:
                    surah_name_ar = surah_lookup.get('name', '')
                    surah_name_en = surah_lookup.get('englishName', '')
            except Exception:
                pass

            first_reciter = reciter_subfolders[0] if reciter_subfolders else ''
            seo_context = {
                'surah_number': surah_number,
                'surah_name_ar': surah_name_ar,
                'surah_name_en': surah_name_en,
                'verse_from': verse_from,
                'verse_to': verse_to,
                'reciter_name': get_reciter_display_name(first_reciter),
                'reciter_subfolder': first_reciter,
                'video_format': video_format,
                'platform_preset': preset['label'],
                'verse_samples': verse_contexts[:12]
            }

            metadata, used_fallback, seo_error = youtube_seo.generate_youtube_seo(
                context=seo_context,
                api_key=config.GEMINI_API_KEY,
                timeout_sec=config.SEO_TIMEOUT_SEC,
                max_retries=config.SEO_MAX_RETRIES
            )
            metadata['used_fallback'] = used_fallback

            base_name = os.path.splitext(output_filename)[0]
            seo_json_filename = f"{base_name}.seo.json"
            seo_txt_filename = f"{base_name}.youtube.txt"
            seo_json_path = os.path.join(config.OUTPUTS_DIR, seo_json_filename)
            seo_txt_path = os.path.join(config.OUTPUTS_DIR, seo_txt_filename)

            metadata_with_context = {
                'video_file': output_filename,
                'context': seo_context,
                'metadata': metadata
            }

            try:
                with open(seo_json_path, 'w', encoding='utf-8') as jf:
                    json.dump(metadata_with_context, jf, ensure_ascii=False, indent=2)

                with open(seo_txt_path, 'w', encoding='utf-8') as tf:
                    tf.write(youtube_seo.build_youtube_text(metadata))

                generation_progress['seo_status'] = 'completed' if not used_fallback else 'fallback'
                generation_progress['seo_message'] = 'تم إنشاء بيانات يوتيوب بنجاح'
                generation_progress['seo_file'] = seo_json_filename
                generation_progress['seo_text_file'] = seo_txt_filename
                generation_progress['seo_data'] = metadata
            except Exception as seo_file_exc:
                generation_progress['seo_status'] = 'failed'
                generation_progress['seo_message'] = f'فشل حفظ بيانات SEO: {str(seo_file_exc)}'
                generation_progress['seo_data'] = metadata

            if seo_error and used_fallback:
                generation_progress['seo_message'] = 'تم استخدام قالب احتياطي لبيانات SEO'
        else:
            generation_progress['seo_status'] = 'disabled'
            generation_progress['seo_message'] = 'ميزة SEO غير مفعلة'

        # 6. Final Cleanup
        shutil.rmtree(segments_dir)

        generation_progress['progress'] = 100
        generation_progress['status'] = 'completed'
        generation_progress['message'] = 'تم إنشاء الفيديو بنجاح!'
        generation_progress['video_path'] = output_filename
        
        return output_filename

    except Exception as e:
        generation_progress['status'] = 'error'
        generation_progress['message'] = f'خطأ: {str(e)}'
        if generation_progress.get('seo_status') == 'running':
            generation_progress['seo_status'] = 'failed'
            generation_progress['seo_message'] = 'توقفت عملية SEO بسبب خطأ في التوليد'
        print(f"Generation Error: {e}")
        # Cleanup segments even on fail
        try:
            if os.path.exists(segments_dir):
                shutil.rmtree(segments_dir)
        except:
            pass
        return None

# --- Routes ---

@app.route('/')
def index():
    ui_path = resource_path('UI.html')
    return send_file(ui_path)

@app.route('/api/reciters', methods=['GET'])
def get_reciters():
    return json_success(fetch_reciters_list())

@app.route('/api/surahs', methods=['GET'])
def get_surahs():
    return json_success(fetch_surahs_list())

@app.route('/api/backgrounds', methods=['GET'])
def get_backgrounds():
    """Return all available video files in vision directory"""
    try:
        if not os.path.exists(config.VISION_DIR):
            return json_error('Vision directory not found', 404)

        return json_success(list_media_files(config.VISION_DIR, SUPPORTED_VIDEO_EXTENSIONS))
    except Exception as e:
        return json_error(str(e), 500)

@app.route('/api/background-audio', methods=['GET'])
def get_background_audio():
    """Return all available audio files in background_audio directory"""
    try:
        files = list_media_files(
            config.BACKGROUND_AUDIO_DIR,
            SUPPORTED_BACKGROUND_AUDIO_EXTENSIONS,
            include_duration=True
        )
        return json_success(files)
    except Exception as e:
        return json_error(str(e), 500)

@app.route('/api/background-audio/<path:filename>', methods=['GET'])
def serve_background_audio(filename):
    """Serve background audio file for preview"""
    return send_from_directory(config.BACKGROUND_AUDIO_DIR, filename)

@app.route('/api/generate', methods=['POST'])
def generate_video_endpoint():
    try:
        data = request.get_json(silent=True) or {}
        try:
            generation_request = parse_generation_request(data)
        except ValueError as exc:
            return json_error(str(exc), 400)

        if not generation_lock.acquire(blocking=False):
            return json_error('A video is already being generated. Please wait until it finishes.', 409)

        def run_generation():
            try:
                generate_video(
                    generation_request['reciters'],
                    generation_request['surah_number'],
                    generation_request['verse_from'],
                    generation_request['verse_to'],
                    generation_request['video_format'],
                    generation_request['custom_bgs'],
                    generation_request['bg_audio'],
                    generation_request['bg_audio_volume'],
                    generation_request['platform_preset']
                )
            finally:
                generation_lock.release()

        # Start in thread
        thread = threading.Thread(target=run_generation, daemon=True)
        thread.start()
        return json_success(message='Started')
    except Exception as e:
        return json_error(str(e), 500)

@app.route('/api/vision/<path:filename>', methods=['GET'])
def serve_vision_file(filename):
    """Serve background video file for preview"""
    return send_from_directory(config.VISION_DIR, filename)

@app.route('/api/progress', methods=['GET'])
def get_progress():
    return jsonify(generation_progress)


@app.route('/api/seo/<path:video_filename>', methods=['GET'])
def get_video_seo(video_filename):
    """Return SEO metadata json for a generated video."""
    try:
        video_name = os.path.basename(video_filename)
        base_name = os.path.splitext(video_name)[0]
        seo_file = f"{base_name}.seo.json"
        seo_path = os.path.normpath(os.path.join(config.OUTPUTS_DIR, seo_file))
        outputs_norm = os.path.normpath(config.OUTPUTS_DIR)

        if not is_safe_child_path(outputs_norm, seo_path):
            return json_error('Invalid path', 400)
        if not os.path.exists(seo_path):
            return json_error('SEO metadata not found', 404)

        with open(seo_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return json_success(data)
    except Exception as e:
        return json_error(str(e), 500)

@app.route('/api/clean', methods=['POST'])
def clean_files():
    """Delete all files in outputs and audio directories"""
    try:
        deleted_count = 0
        errors = []
        
        # Clean outputs directory
        if os.path.exists(config.OUTPUTS_DIR):
            for filename in os.listdir(config.OUTPUTS_DIR):
                file_path = os.path.join(config.OUTPUTS_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted_count += 1
                except Exception as e:
                    errors.append(f"Error deleting {filename}: {str(e)}")
        
        # Clean audio directory
        if os.path.exists(config.AUDIO_DIR):
            for filename in os.listdir(config.AUDIO_DIR):
                file_path = os.path.join(config.AUDIO_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted_count += 1
                except Exception as e:
                    errors.append(f"Error deleting {filename}: {str(e)}")
        
        message = f'تم مسح {deleted_count} ملف بنجاح'
        if errors:
            message = f'{message}، مع بعض الأخطاء'

        return json_success(message=message, deleted_count=deleted_count, errors=errors)
            
    except Exception as e:
        return json_error(f'خطأ في مسح الملفات: {str(e)}', 500)

@app.route('/api/library', methods=['GET'])
def get_library_videos():
    try:
        if not os.path.exists(config.OUTPUTS_DIR):
            return json_success([])
            
        files = []
        for f in os.listdir(config.OUTPUTS_DIR):
            if f.lower().endswith(SUPPORTED_LIBRARY_EXTENSIONS):
                file_path = os.path.join(config.OUTPUTS_DIR, f)
                if not os.path.isfile(file_path):
                    continue
                stat = os.stat(file_path)
                files.append({
                    'name': f,
                    'size': stat.st_size,
                    'created_at': stat.st_ctime
                })
        
        # Sort by creation time descending (newest first)
        files.sort(key=lambda x: x['created_at'], reverse=True)
        return json_success(files)
    except Exception as e:
        return json_error(str(e), 500)

@app.route('/api/library/<filename>', methods=['DELETE'])
def delete_library_video(filename):
    try:
        # Sanitize filename
        filename = os.path.basename(filename)
        file_path = os.path.normpath(os.path.join(config.OUTPUTS_DIR, filename))
        
        # Ensure path is inside OUTPUTS_DIR (Directory Traversal Protection)
        if not is_safe_child_path(config.OUTPUTS_DIR, file_path):
            return json_error('مسار غير صالح', 400)
            
        if os.path.exists(file_path):
            os.remove(file_path)
            return json_success(message='تم حذف الفيديو بنجاح')
        return json_error('الملف غير موجود', 404)
    except Exception as e:
        return json_error(str(e), 500)

@app.route('/downloads/<path:filename>', methods=['GET'])
def serve_video(filename):
    """Serve video file for viewing (not download)"""
    return send_from_directory(config.OUTPUTS_DIR, filename)

if __name__ == '__main__':
    try:
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "5000"))
        auto_open = os.getenv("AUTO_OPEN_BROWSER", "1").strip().lower() not in {"0", "false", "no"}

        if auto_open:
            def open_browser():
                time.sleep(1.5)
                webbrowser.open(f"http://127.0.0.1:{port}")

            threading.Thread(target=open_browser, daemon=True).start()

        print(f"Server running on http://{host}:{port}")
        app.run(debug=False, host=host, port=port)
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        input("\nPress Enter to exit...")
