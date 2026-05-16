import requests
import os

reciters = [
    'Abdul_Basit_Murattal_192kbps',
    'Husary_64kbps',
    'Minshawy_Murattal_128kbps',
    'Fares_Abbad_64kbps',
    'Yasser_Ad-Dussary_128kbps',
    'MaherAlMuaiqly128kbps',
    'MAHMOUD_ALI_AL_BANNA_32KBPS'
]

surah = 1
for i, reciter in enumerate(reciters):
    verse = i + 1
    url = f"https://everyayah.com/data/{reciter}/{surah:03d}{verse:03d}.mp3"
    print(f"Checking {reciter} -> Verse {verse}: {url}")
    try:
        r = requests.head(url, timeout=10)
        print(f"Status: {r.status_code}, Size: {r.headers.get('content-length')}")
    except Exception as e:
        print(f"Error: {e}")
