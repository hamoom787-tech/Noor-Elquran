"""
Quran Reels Video Generator - Backend Server
Flask server for generating short Reels videos of Quran verses
"""

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
import arabic_reshaper
from bidi.algorithm import get_display
import math

from quranreels import config
import sys
import threading

# Check if running on mobile (BeeWare)
IS_MOBILE = hasattr(sys, 'getandroidapilevel') or 'iOS' in str(sys.platform) or os.environ.get('BRIEFCASE_APP_NAME')

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev, PyInstaller, and BeeWare """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        if IS_MOBILE:
            # For BeeWare mobile apps, use the app's resource directory
            # BeeWare stores resources in the app bundle
            try:
                import platform
                if platform.system() == 'Android':
                    # Android: resources are in assets
                    base_path = os.path.join(os.path.dirname(sys.executable), 'app', 'src', 'main', 'assets')
                else:
                    # iOS: resources are in the app bundle
                    base_path = os.path.dirname(sys.executable)
            except:
                base_path = os.path.abspath(".")
        else:
            base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

app = Flask(__name__)
CORS(app)

# Global variable to track generation progress
generation_progress = {
    'status': 'idle',
    'progress': 0,
    'message': '',
    'video_path': None
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
    
    # Save to cache just in case, though we use static return
    try:
        cache_file = os.path.join(config.DATA_DIR, 'reciters.json')
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(reciters, f, ensure_ascii=False, indent=2)
    except:
        pass
        
    return reciters

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

import re

# ... (Imports remain same) ...

def fetch_verse_text(surah_number, verse_number):
    """Fetch Uthmani Quran text AND English Translation"""
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
                    # The Uthmani Bismillah usually length is ~38-40 chars
                    basmala = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
                    if int(surah_number) != 1 and int(verse_number) == 1:
                        if text.startswith(basmala):
                            text = text[len(basmala):].strip()
                    result['arabic'] = text
                elif edition['edition']['identifier'] == 'en.sahih':
                    result['english'] = text
            return result
        return None
    except Exception as e:
        print(f"Error fetching verse text: {e}")
        return None

# ... (Imports remain same) ...

# Restore missing audio functions

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

def analyze_audio_timing(audio_path, words_list):
    """
    Analyze audio to determine word-level timing based on silence detection and speech rate.
    Returns a list of tuples: [(word, start_time, end_time), ...]
    """
    try:
        from pydub import AudioSegment
        import numpy as np
        
        # Load audio file
        audio = AudioSegment.from_file(audio_path)
        duration_ms = len(audio)
        duration_sec = duration_ms / 1000.0
        
        # Convert to numpy array for analysis
        samples = np.array(audio.get_array_of_samples())
        if audio.channels == 2:
            # Convert stereo to mono by averaging
            samples = samples.reshape((-1, 2)).mean(axis=1)
        
        # Normalize samples to float32 range [-1, 1]
        if samples.dtype == np.int16:
            samples = samples.astype(np.float32) / 32768.0
        elif samples.dtype == np.int32:
            samples = samples.astype(np.float32) / 2147483648.0
        
        # Calculate frame size (10ms windows)
        frame_size = int(audio.frame_rate * 0.01)  # 10ms frames
        num_frames = len(samples) // frame_size
        
        # Calculate RMS energy for each frame
        rms_values = []
        for i in range(num_frames):
            start_idx = i * frame_size
            end_idx = min(start_idx + frame_size, len(samples))
            frame = samples[start_idx:end_idx]
            rms = np.sqrt(np.mean(frame ** 2))
            rms_db = 20 * np.log10(rms + 1e-10)  # Convert to dB
            rms_values.append(rms_db)
        
        rms_values = np.array(rms_values)
        
        # Detect silence regions
        silence_threshold_db = config.SILENCE_THRESHOLD
        is_silence = rms_values < silence_threshold_db
        
        # Find silence boundaries (where silence starts/ends)
        silence_starts = []
        silence_ends = []
        in_silence = False
        min_silence_frames = int(config.MIN_SILENCE_DURATION / 0.01)  # Convert to frames
        
        for i in range(len(is_silence)):
            if is_silence[i] and not in_silence:
                # Start of silence
                silence_starts.append(i)
                in_silence = True
            elif not is_silence[i] and in_silence:
                # End of silence
                if i - silence_starts[-1] >= min_silence_frames:
                    silence_ends.append(i)
                else:
                    # Too short, ignore
                    silence_starts.pop()
                in_silence = False
        
        # If we ended in silence, add the end
        if in_silence and len(silence_starts) > len(silence_ends):
            silence_ends.append(len(is_silence))
        
        # Calculate word timings
        num_words = len(words_list)
        if num_words == 0:
            return []
        
        # Calculate average speech rate
        # Total speech time = total duration - silence time
        total_silence_time = sum((silence_ends[i] - silence_starts[i]) * 0.01 
                                 for i in range(len(silence_ends)))
        speech_time = duration_sec - total_silence_time
        
        if speech_time <= 0:
            speech_time = duration_sec
        
        # Average time per word
        avg_time_per_word = speech_time / num_words if num_words > 0 else duration_sec
        
        # Build word timings
        word_timings = []
        current_time = 0.0
        
        for i, word in enumerate(words_list):
            # Check if there's a silence before this word
            word_start_time = current_time
            
            # If we're near a silence region, adjust timing
            for j, silence_start in enumerate(silence_starts):
                silence_start_time = silence_start * 0.01
                silence_end_time = silence_ends[j] * 0.01 if j < len(silence_ends) else duration_sec
                
                # If current time is within silence, skip to end of silence
                if silence_start_time <= current_time < silence_end_time:
                    current_time = silence_end_time
                    word_start_time = current_time
                    break
            
            # Calculate word duration based on speech rate
            # Longer words might take slightly more time
            word_length_factor = 1.0 + (len(word) / 20.0)  # Slight adjustment for word length
            word_duration = avg_time_per_word * word_length_factor
            
            # Ensure we don't exceed total duration
            if word_start_time + word_duration > duration_sec:
                word_duration = duration_sec - word_start_time
            
            word_end_time = word_start_time + word_duration
            
            word_timings.append({
                'word': word,
                'start': word_start_time,
                'end': word_end_time
            })
            
            current_time = word_end_time
        
        return word_timings
        
    except ImportError:
        print("Warning: pydub or numpy not available. Using fallback timing method.")
        # Fallback: simple uniform distribution
        duration = get_audio_duration(audio_path)
        num_words = len(words_list)
        if num_words == 0:
            return []
        
        avg_time_per_word = duration / num_words
        word_timings = []
        current_time = 0.0
        
        for word in words_list:
            word_timings.append({
                'word': word,
                'start': current_time,
                'end': current_time + avg_time_per_word
            })
            current_time += avg_time_per_word
        
        return word_timings
    except Exception as e:
        print(f"Error analyzing audio timing: {e}")
        # Fallback: simple uniform distribution
        duration = get_audio_duration(audio_path)
        num_words = len(words_list)
        if num_words == 0:
            return []
        
        avg_time_per_word = duration / num_words
        word_timings = []
        current_time = 0.0
        
        for word in words_list:
            word_timings.append({
                'word': word,
                'start': current_time,
                'end': current_time + avg_time_per_word
            })
            current_time += avg_time_per_word
        
        return word_timings

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

def create_text_chunk_image(chunk_data, width, height, output_path):
    """
    Create text image with Arabic (Gold Diacritics) AND English Translation using Pillow.
    chunk_data: {'arabic': '...', 'english': '...'} or just string (legacy support)
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import arabic_reshaper
        from bidi.algorithm import get_display
        
        # Handle legacy string input if any
        if isinstance(chunk_data, str):
            chunk_data = {'arabic': chunk_data, 'english': ''}
            
        arabic_text = chunk_data.get('arabic', '')
        english_text = chunk_data.get('english', '')
        
        # Create transparent image
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Try to load fonts
        try:
            # Try to use system fonts - fallback to default if not available
            arabic_font = ImageFont.truetype(config.TEXT_FONT, config.TEXT_FONT_SIZE) if os.path.exists(config.TEXT_FONT) else ImageFont.load_default()
        except:
            try:
                # Try common Arabic font paths
                font_paths = [
                    'C:/Windows/Fonts/arial.ttf',
                    'C:/Windows/Fonts/tahoma.ttf',
                    '/System/Library/Fonts/Supplemental/Arial.ttf',  # macOS
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # Linux
                ]
                arabic_font = None
                for path in font_paths:
                    if os.path.exists(path):
                        arabic_font = ImageFont.truetype(path, config.TEXT_FONT_SIZE)
                        break
                if not arabic_font:
                    arabic_font = ImageFont.load_default()
            except:
                arabic_font = ImageFont.load_default()
        
        try:
            english_font = ImageFont.truetype('arial.ttf', config.TRANSLATION_FONT_SIZE)
        except:
            english_font = ImageFont.load_default()
        
        # Process Arabic text with reshaping and bidi
        if arabic_text:
            # Add brackets
            arabic_text = f"﴿ {arabic_text} ﴾"
            # Reshape Arabic text
            reshaped_text = arabic_reshaper.reshape(arabic_text)
            # Apply bidi algorithm
            bidi_text = get_display(reshaped_text)
        else:
            bidi_text = ""
        
        # Calculate text positions
        y_position = height // 2
        padding = 25
        
        # Draw Arabic text with shadow effect
        if bidi_text:
            # Get text bounding box
            bbox = draw.textbbox((0, 0), bidi_text, font=arabic_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Center horizontally
            x_position = (width - text_width) // 2
            
            # Draw shadow (black, slightly offset)
            shadow_offset = 3
            draw.text((x_position + shadow_offset, y_position - text_height // 2 + shadow_offset), 
                     bidi_text, font=arabic_font, fill=(0, 0, 0, 200))
            
            # Draw main text (white)
            draw.text((x_position, y_position - text_height // 2), 
                     bidi_text, font=arabic_font, fill=config.TEXT_COLOR)
        
        # Draw English translation below Arabic
        if english_text:
            # Get English text bounding box
            en_bbox = draw.textbbox((0, 0), english_text, font=english_font)
            en_text_width = en_bbox[2] - en_bbox[0]
            en_text_height = en_bbox[3] - en_bbox[1]
            
            # Center horizontally
            en_x_position = (width - en_text_width) // 2
            en_y_position = y_position + text_height // 2 + 20 if bidi_text else y_position
            
            # Draw English shadow
            draw.text((en_x_position + shadow_offset, en_y_position + shadow_offset), 
                     english_text, font=english_font, fill=(0, 0, 0, 200))
            
            # Draw English text
            draw.text((en_x_position, en_y_position), 
                     english_text, font=english_font, fill='white')
        
        # Save image
        img.save(output_path, 'PNG')
        return True

    except Exception as e:
        print(f"Error creating text image with Pillow: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- Video Generation ---

def render_verse_segment(background_video, audio_path, overlay_configs, total_duration, output_segment_path, width, height, do_fade_in=False, do_fade_out=False):
    """
    Renders a single verse segment into a .ts file (better for concatenation).
    """
    try:
        cmd = [config.FFMPEG_PATH]
        
        # Input 0: Background (Infinite loop)
        cmd.extend(['-stream_loop', '-1', '-i', background_video])
        
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
            overlay_cmd = f"[{last_bg_label}][{text_label}]overlay=(W-w)/2:(H-h)/2:enable='between(t,{start},{end})':shortest=1[{next_bg_label}];"
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

def generate_video(reciter_subfolders, surah_number, verse_from, verse_to, video_format='portrait'):
    """
    reciter_subfolders: List of strings (single reciter)
    video_format: 'portrait' (9:16), 'landscape' (16:9), or 'square' (1:1)
    """
    global generation_progress
    
    # Presets for width and height
    PRESETS = {
        'portrait': (720, 1280),
        'landscape': (1280, 720),
        'square': (720, 720)
    }
    width, height = PRESETS.get(video_format, PRESETS['portrait'])
    
    # Ensure reciter_subfolders is a list
    if isinstance(reciter_subfolders, str):
        reciter_subfolders = [reciter_subfolders]
    
    segments_dir = os.path.join(config.DATA_DIR, f"temp_segments_{int(time.time())}")
    os.makedirs(segments_dir, exist_ok=True)
    
    try:
        generation_progress['status'] = 'running'
        generation_progress['progress'] = 5
        generation_progress['message'] = 'تحليل البيانات وتجهيز الملفات...'
        
        # 1. Prepare Background Selection
        background_videos = list(Path(config.VISION_DIR).glob('*.mp4'))
        if not background_videos:
            raise Exception("No background videos found in vision/")
            
        # --- Persistent Background Logic ---
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
        
        # If we ran out of new backgrounds (or have fewer than needed for this video), reset logic
        # We need 'total_verses' distinct backgrounds if possible
        verse_count = verse_to - verse_from + 1
        
        if len(available_bgs) < verse_count:
            print("Resetting used backgrounds list to ensure variety.")
            used_bgs = []
            available_bgs = [str(bg) for bg in background_videos]

        # Shuffle available backgrounds
        random.shuffle(available_bgs)
        
        # Select backgrounds for this project
        # If still not enough (e.g. video needs 10 verses, but we only have 5 videos total), we must cycle
        selected_project_bgs = []
        for k in range(verse_count):
            selected_project_bgs.append(available_bgs[k % len(available_bgs)])
            
        # Update used list
        # We only add unique ones that were actually 'new' usage to the persistence file
        # But for simplicity, let's just mark everything we use now as used.
        for bg in selected_project_bgs:
            if bg not in used_bgs:
                used_bgs.append(bg)
                
        # Save updated used list
        with open(used_bg_file, 'w', encoding='utf-8') as f:
            json.dump(used_bgs, f, ensure_ascii=False, indent=2)
            
        # -----------------------------------
        
        verse_data = [] # List of config dicts
        total_verses = verse_to - verse_from + 1
        
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
            
            # Analyze audio timing for real synchronization
            arabic_words = text_obj['arabic'].split()
            word_timings = analyze_audio_timing(audio_path, arabic_words)
            
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

            # 3. Render THIS verse segment immediately with its background
            segment_path = os.path.join(segments_dir, f"segment_{i:04d}.ts")
            # Log which reciter is being used for this verse
            print(f"Verse {verse_num} - Reciter: {current_reciter} - Format: {video_format}")
            generation_progress['message'] = f'توليد فيديو الآية {verse_num}...'
            if not render_verse_segment(background_video, audio_path, verse_overlay_configs, duration, segment_path, width, height, do_fade_in=do_fade_in, do_fade_out=do_fade_out):
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
        
        output_filename = f"quran_video_{int(time.time())}.mp4"
        output_path = os.path.join(config.OUTPUTS_DIR, output_filename)
        
        concat_cmd = [
            config.FFMPEG_PATH, '-f', 'concat', '-safe', '0',
            '-i', concat_file, '-c', 'copy', '-y', output_path
        ]
        subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # 5. Final Cleanup
        shutil.rmtree(segments_dir)

        generation_progress['progress'] = 100
        generation_progress['status'] = 'completed'
        generation_progress['message'] = 'تم إنشاء الفيديو بنجاح!'
        generation_progress['video_path'] = output_filename
        
        return output_filename

    except Exception as e:
        generation_progress['status'] = 'error'
        generation_progress['message'] = f'خطأ: {str(e)}'
        print(f"Generation Error: {e}")
        # Cleanup segments even on fail
        if os.path.exists(segments_dir):
            shutil.rmtree(segments_dir)
        return None

# --- Routes ---

@app.route('/')
def index():
    ui_path = resource_path('UI.html')
    return send_file(ui_path)

@app.route('/api/reciters', methods=['GET'])
def get_reciters():
    return jsonify({'success': True, 'data': fetch_reciters_list()})

@app.route('/api/surahs', methods=['GET'])
def get_surahs():
    return jsonify({'success': True, 'data': fetch_surahs_list()})

@app.route('/api/generate', methods=['POST'])
def generate_video_endpoint():
    try:
        data = request.json
        # Handling single reciter (string or list)
        reciters = data.get('reciter_subfolder')
        if not reciters:
            return jsonify({'success': False, 'error': 'No reciter selected'}), 400
            
        # Ensure it's a list (for compatibility)
        if isinstance(reciters, str):
            reciters = [reciters]
            
        # Start in thread
        import threading
        thread = threading.Thread(target=generate_video, args=(
            reciters,
            int(data.get('surah_number')),
            int(data.get('verse_from')),
            int(data.get('verse_to')),
            data.get('video_format', 'portrait')
        ))
        thread.start()
        return jsonify({'success': True, 'message': 'Started'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/progress', methods=['GET'])
def get_progress():
    return jsonify(generation_progress)

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
        
        if errors:
            return jsonify({
                'success': True,
                'message': f'تم مسح {deleted_count} ملف بنجاح، مع بعض الأخطاء',
                'deleted_count': deleted_count,
                'errors': errors
            }), 200
        else:
            return jsonify({
                'success': True,
                'message': f'تم مسح {deleted_count} ملف بنجاح',
                'deleted_count': deleted_count
            }), 200
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'خطأ في مسح الملفات: {str(e)}'
        }), 500

@app.route('/downloads/<path:filename>', methods=['GET'])
def serve_video(filename):
    """Serve video file for viewing (not download)"""
    return send_from_directory(config.OUTPUTS_DIR, filename)

if __name__ == '__main__':
    try:
        # For mobile apps, don't open browser (handled by WebView)
        if not IS_MOBILE:
            # Auto-open browser in a separate thread (desktop only)
            try:
                import webbrowser
                def open_browser():
                    time.sleep(1.5)
                    webbrowser.open("http://127.0.0.1:5000")
                threading.Thread(target=open_browser).start()
                print("Server running on http://localhost:5000")
                print("Opening browser...")
            except:
                print("Server running on http://127.0.0.1:5000")
        else:
            print("Mobile app mode - Server running on http://127.0.0.1:5000")
        
        app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False)
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        if not IS_MOBILE:
            input("\nPress Enter to exit...")
