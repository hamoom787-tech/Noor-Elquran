"""
YouTube SEO metadata generation helpers.
Produces a publishing pack for Quranic videos: titles, descriptions, hashtags,
upload tags, pinned comment, thumbnail text, and retention notes.
"""

import json
import re
from typing import Dict, List, Tuple

import requests


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


def _sanitize_text(value: str, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    clean = re.sub(r"\s+", " ", value).strip()
    return clean[:max_len].strip()


def _normalize_hashtags(hashtags: List[str]) -> List[str]:
    normalized = []
    seen = set()
    for tag in hashtags or []:
        if not isinstance(tag, str):
            continue
        clean = re.sub(r"[^#\w\u0600-\u06FF]", "", tag).strip()
        if not clean:
            continue
        if not clean.startswith("#"):
            clean = f"#{clean}"
        clean = clean[:60]
        lowered = clean.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(clean)
        if len(normalized) >= 15:
            break
    return normalized


def _normalize_keywords(keywords: List[str]) -> List[str]:
    normalized = []
    seen = set()
    for kw in keywords or []:
        clean = _sanitize_text(kw, 80)
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(clean)
        if len(normalized) >= 25:
            break
    return normalized


def _normalize_string_list(values: List[str], max_items: int, max_len: int) -> List[str]:
    normalized = []
    seen = set()
    for value in values or []:
        clean = _sanitize_text(value, max_len)
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(clean)
        if len(normalized) >= max_items:
            break
    return normalized


def _compact_join(parts: List[str], separator: str = " ") -> str:
    return separator.join([part.strip() for part in parts if isinstance(part, str) and part.strip()]).strip()


def _extract_json(raw_text: str) -> Dict:
    if not raw_text:
        raise ValueError("Empty Gemini response")

    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise ValueError("No JSON object found in Gemini response")
        text = text[first:last + 1]

    return json.loads(text)


def normalize_metadata(payload: Dict) -> Dict:
    title_ar = _sanitize_text(payload.get("title_ar", ""), 100)
    title_en = _sanitize_text(payload.get("title_en", ""), 100)
    description_ar = _sanitize_text(payload.get("description_ar", ""), 4500)
    description_en = _sanitize_text(payload.get("description_en", ""), 4500)
    title_variants_ar = _normalize_string_list(payload.get("title_variants_ar", []), 5, 100)
    title_variants_en = _normalize_string_list(payload.get("title_variants_en", []), 5, 100)
    hook_ar = _sanitize_text(payload.get("hook_ar", ""), 180)
    hook_en = _sanitize_text(payload.get("hook_en", ""), 180)
    thumbnail_text_ar = _sanitize_text(payload.get("thumbnail_text_ar", ""), 45)
    thumbnail_text_en = _sanitize_text(payload.get("thumbnail_text_en", ""), 45)
    pinned_comment_ar = _sanitize_text(payload.get("pinned_comment_ar", ""), 500)
    pinned_comment_en = _sanitize_text(payload.get("pinned_comment_en", ""), 500)
    call_to_action_ar = _sanitize_text(payload.get("call_to_action_ar", ""), 180)
    call_to_action_en = _sanitize_text(payload.get("call_to_action_en", ""), 180)
    hashtags_primary = _normalize_hashtags(payload.get("hashtags_primary", []))
    hashtags_ar = _normalize_hashtags(payload.get("hashtags_ar", []))
    hashtags_en = _normalize_hashtags(payload.get("hashtags_en", []))
    hashtags = _normalize_hashtags(
        payload.get("hashtags", []) + hashtags_primary + hashtags_ar + hashtags_en
    )
    keywords = _normalize_keywords(payload.get("keywords", []))
    upload_tags = _normalize_string_list(payload.get("upload_tags", []), 30, 55)
    retention_tips = _normalize_string_list(payload.get("retention_tips", []), 6, 140)
    publish_checklist = _normalize_string_list(payload.get("publish_checklist", []), 8, 120)

    if not title_ar:
        title_ar = "تلاوة قرآنية مؤثرة | آيات مختارة"
    if not title_en:
        title_en = "Emotional Quran Recitation | Selected Verses"
    if not description_ar:
        description_ar = "استمع إلى تلاوة قرآنية خاشعة مع آيات مختارة بجودة عالية."
    if not description_en:
        description_en = "Listen to a calm Quran recitation with selected verses in high quality."
    if not hook_ar:
        hook_ar = title_ar
    if not hook_en:
        hook_en = title_en
    if not thumbnail_text_ar:
        thumbnail_text_ar = "تلاوة خاشعة"
    if not thumbnail_text_en:
        thumbnail_text_en = "Quran Recitation"
    if not pinned_comment_ar:
        pinned_comment_ar = "اكتب الآية التي لامست قلبك، ولا تنس مشاركة المقطع لنشر الخير."
    if not pinned_comment_en:
        pinned_comment_en = "Share the verse that touched your heart, and pass this reminder on."
    if not call_to_action_ar:
        call_to_action_ar = "اشترك ليصلك المزيد من التلاوات القصيرة الهادئة."
    if not call_to_action_en:
        call_to_action_en = "Subscribe for more peaceful Quran shorts."
    if not hashtags:
        hashtags = ["#quran", "#القرآن", "#tilawah", "#quranrecitation"]
    if not hashtags_primary:
        hashtags_primary = hashtags[:5]
    if not hashtags_ar:
        hashtags_ar = [tag for tag in hashtags if re.search(r"[\u0600-\u06FF]", tag)]
    if not hashtags_en:
        hashtags_en = [tag for tag in hashtags if not re.search(r"[\u0600-\u06FF]", tag)]
    if not keywords:
        keywords = [
            "Quran recitation",
            "تلاوة القرآن",
            "Quran verses",
            "Islamic reminder",
        ]
    if not upload_tags:
        upload_tags = keywords[:]
    if not title_variants_ar:
        title_variants_ar = [title_ar]
    if not title_variants_en:
        title_variants_en = [title_en]
    if not retention_tips:
        retention_tips = [
            "ابدأ الفيديو مباشرة بالتلاوة بدون مقدمة طويلة.",
            "اجعل النص واضحًا وفي منطقة آمنة بعيدًا عن أزرار المنصة.",
            "استخدم أول سطر في الوصف كجملة مؤثرة قصيرة.",
        ]
    if not publish_checklist:
        publish_checklist = [
            "راجع صحة السورة والآيات قبل النشر.",
            "اختر أفضل عنوان من بدائل العناوين.",
            "ضع أهم 3 هاشتاجات في أول الوصف.",
            "ثبّت التعليق المقترح بعد النشر.",
        ]

    return {
        "title_ar": title_ar,
        "title_en": title_en,
        "title_variants_ar": title_variants_ar,
        "title_variants_en": title_variants_en,
        "hook_ar": hook_ar,
        "hook_en": hook_en,
        "description_ar": description_ar,
        "description_en": description_en,
        "thumbnail_text_ar": thumbnail_text_ar,
        "thumbnail_text_en": thumbnail_text_en,
        "pinned_comment_ar": pinned_comment_ar,
        "pinned_comment_en": pinned_comment_en,
        "call_to_action_ar": call_to_action_ar,
        "call_to_action_en": call_to_action_en,
        "hashtags_primary": hashtags_primary[:8],
        "hashtags_ar": hashtags_ar[:10],
        "hashtags_en": hashtags_en[:10],
        "hashtags": hashtags,
        "keywords": keywords,
        "upload_tags": upload_tags,
        "retention_tips": retention_tips,
        "publish_checklist": publish_checklist,
    }


def build_fallback_metadata(context: Dict) -> Dict:
    surah_ar = context.get("surah_name_ar", "سورة من القرآن")
    surah_en = context.get("surah_name_en", "Quran Surah")
    verse_from = context.get("verse_from")
    verse_to = context.get("verse_to")
    reciter_name = context.get("reciter_name", "قارئ مميز")
    platform = context.get("platform_preset", "YouTube Shorts")
    verse_samples = context.get("verse_samples", [])
    sample_ar = ""
    if verse_samples:
        sample_ar = _sanitize_text(verse_samples[0].get("arabic", ""), 140)

    verse_range_ar = f"{verse_from}-{verse_to}" if verse_from and verse_to else ""
    verse_range_en = f"{verse_from}-{verse_to}" if verse_from and verse_to else ""
    verse_label_ar = f"الآيات {verse_range_ar}" if verse_range_ar else "آيات مختارة"
    verse_label_en = f"Verses {verse_range_en}" if verse_range_en else "Selected Verses"

    hook_ar = f"تلاوة خاشعة من {surah_ar} {verse_label_ar} بصوت {reciter_name}"
    hook_en = f"Peaceful Quran recitation from {surah_en} {verse_label_en}"
    source_ar = f"{surah_ar} - {verse_label_ar}"
    source_en = f"{surah_en} - {verse_label_en}"
    sample_block_ar = f"\n\n{sample_ar}" if sample_ar else ""

    fallback = {
        "title_ar": f"{surah_ar} {verse_label_ar} | تلاوة خاشعة بصوت {reciter_name}",
        "title_en": f"{surah_en} {verse_label_en} | Peaceful Quran Recitation",
        "title_variants_ar": [
            f"تلاوة مؤثرة من {surah_ar} {verse_label_ar}",
            f"{surah_ar} بصوت {reciter_name} | راحة وطمأنينة",
            f"آيات هادئة من {surah_ar} | قرآن كريم",
            f"تدبر {surah_ar} {verse_label_ar} | تلاوة قصيرة",
        ],
        "title_variants_en": [
            f"{surah_en} {verse_label_en} | Calm Quran Recitation",
            f"Peaceful Quran Short | {surah_en}",
            f"Quran Recitation for the Heart | {surah_en}",
            f"Listen and Reflect | {surah_en} {verse_label_en}",
        ],
        "hook_ar": hook_ar,
        "hook_en": hook_en,
        "description_ar": (
            f"{hook_ar}\n\n"
            f"المصدر: {source_ar}\n"
            f"القارئ: {reciter_name}\n"
            f"المنصة المقترحة: {platform}"
            f"{sample_block_ar}\n\n"
            "مقطع قصير للتدبر والطمأنينة. شاركه مع من تحب ليصل الأجر بإذن الله.\n\n"
            "اشترك وفعل التنبيهات ليصلك المزيد من التلاوات القرآنية القصيرة."
        ),
        "description_en": (
            f"{hook_en}\n\n"
            f"Source: {source_en}\n"
            f"Reciter: {reciter_name}\n"
            f"Suggested platform: {platform}\n\n"
            "A short reminder for reflection and calm. Share it with someone who may need it today.\n\n"
            "Subscribe for more Quran shorts and peaceful Islamic reminders."
        ),
        "thumbnail_text_ar": f"{surah_ar} {verse_range_ar}".strip(),
        "thumbnail_text_en": f"{surah_en} Quran",
        "pinned_comment_ar": f"ما الآية التي لامست قلبك من {surah_ar}؟ اكتبها وشارك المقطع لنشر الخير.",
        "pinned_comment_en": f"Which verse from {surah_en} touched your heart? Share this reminder with someone.",
        "call_to_action_ar": "شارك المقطع بنية نشر القرآن، واشترك ليصلك المزيد.",
        "call_to_action_en": "Share this Quran reminder and subscribe for more.",
        "hashtags_primary": ["#القرآن", "#quran", "#quranrecitation", "#shorts", "#تلاوة"],
        "hashtags_ar": ["#القرآن_الكريم", "#تلاوة_خاشعة", "#آيات_قرآنية", "#راحة_نفسية", "#تدبر"],
        "hashtags_en": ["#QuranShorts", "#IslamicReminder", "#Tilawah", "#QuranDaily", "#Muslim"],
        "hashtags": [
            "#القرآن",
            "#تلاوة",
            "#quran",
            "#quranrecitation",
            "#islam",
            "#shorts",
            "#QuranShorts",
            "#تلاوة_خاشعة",
        ],
        "keywords": [
            f"{surah_ar}",
            f"{surah_en}",
            "Quran recitation",
            "Quran shorts",
            "Islamic reminders",
            "تلاوة القرآن",
            "قرآن كريم",
            "تلاوة خاشعة",
            "آيات قرآنية قصيرة",
            f"{reciter_name}",
        ],
        "upload_tags": [
            "Quran",
            "Quran recitation",
            "Quran shorts",
            "Islamic reminder",
            "Tilawah",
            "القرآن الكريم",
            "تلاوة خاشعة",
            f"{surah_ar}",
            f"{surah_en}",
            f"{reciter_name}",
        ],
        "retention_tips": [
            "اجعل أول ثانية تبدأ بالصوت مباشرة بدون مقدمة.",
            "استخدم العنوان الأقصر إذا كان الفيديو Shorts.",
            "ضع أول 3 هاشتاجات في نهاية أول فقرة من الوصف.",
            "ثبّت التعليق المقترح لزيادة التفاعل الهادئ والمحترم.",
        ],
        "publish_checklist": [
            "تأكد من صحة اسم السورة ونطاق الآيات.",
            "اختر عنوانًا واحدًا فقط من بدائل العناوين.",
            "ضع tags في خانة Tags داخل YouTube Studio.",
            "انشر كـ private أولًا وراجع الصوت والنص قبل public.",
        ],
    }
    return normalize_metadata(fallback)


def build_youtube_text(metadata: Dict) -> str:
    return (
        "===== YouTube Publishing Pack =====\n\n"
        "Recommended Arabic Title:\n"
        f"{metadata['title_ar']}\n\n"
        "Recommended English Title:\n"
        f"{metadata['title_en']}\n\n"
        "Arabic Title Variants:\n"
        f"{chr(10).join('- ' + item for item in metadata.get('title_variants_ar', []))}\n\n"
        "English Title Variants:\n"
        f"{chr(10).join('- ' + item for item in metadata.get('title_variants_en', []))}\n\n"
        "Opening Hook:\n"
        f"{metadata.get('hook_ar', '')}\n{metadata.get('hook_en', '')}\n\n"
        "Arabic Description:\n"
        f"{metadata['description_ar']}\n\n"
        "English Description:\n"
        f"{metadata['description_en']}\n\n"
        "Primary Hashtags:\n"
        f"{' '.join(metadata.get('hashtags_primary', []))}\n\n"
        "All Hashtags:\n"
        f"{' '.join(metadata['hashtags'])}\n\n"
        "YouTube Upload Tags:\n"
        f"{', '.join(metadata.get('upload_tags', metadata['keywords']))}\n\n"
        "Keywords:\n"
        f"{', '.join(metadata['keywords'])}\n\n"
        "Pinned Comment Arabic:\n"
        f"{metadata.get('pinned_comment_ar', '')}\n\n"
        "Pinned Comment English:\n"
        f"{metadata.get('pinned_comment_en', '')}\n\n"
        "Thumbnail Text:\n"
        f"{metadata.get('thumbnail_text_ar', '')}\n{metadata.get('thumbnail_text_en', '')}\n\n"
        "Retention Tips:\n"
        f"{chr(10).join('- ' + item for item in metadata.get('retention_tips', []))}\n\n"
        "Publish Checklist:\n"
        f"{chr(10).join('- ' + item for item in metadata.get('publish_checklist', []))}\n"
    )


def generate_youtube_seo(
    context: Dict,
    api_key: str,
    timeout_sec: int = 30,
    max_retries: int = 2,
) -> Tuple[Dict, bool, str]:
    """
    Returns: (metadata, used_fallback, error_message)
    """
    if not api_key:
        return build_fallback_metadata(context), True, "GEMINI_API_KEY is missing"

    prompt = (
        "You are a senior YouTube growth strategist and Arabic copywriter for respectful Quranic short-form videos.\n"
        "Create a high-retention, search-optimized publishing pack for ONE Quran video.\n"
        "Return STRICT JSON only with these exact keys:\n"
        "title_ar, title_en, title_variants_ar, title_variants_en, hook_ar, hook_en,\n"
        "description_ar, description_en, thumbnail_text_ar, thumbnail_text_en,\n"
        "pinned_comment_ar, pinned_comment_en, call_to_action_ar, call_to_action_en,\n"
        "hashtags_primary, hashtags_ar, hashtags_en, hashtags, keywords, upload_tags,\n"
        "retention_tips, publish_checklist\n\n"
        "Strategy rules:\n"
        "- Optimize for YouTube Shorts/Reels/TikTok discovery and retention, but do not promise virality.\n"
        "- Tone must be reverent, calm, truthful, and suitable for Quran content.\n"
        "- No clickbait, no fake miracles, no guilt pressure, no exaggerated religious claims.\n"
        "- Titles must be <=100 chars and front-load searchable terms like Quran, تلاوة, surah name, reciter.\n"
        "- Provide 4-5 alternative titles in Arabic and English for A/B testing.\n"
        "- The first line of each description must work as a strong hook.\n"
        "- Descriptions should include source surah/verses, reciter, soft CTA, and natural keywords.\n"
        "- hashtags_primary: 5-8 strongest tags, mixed Arabic/English.\n"
        "- hashtags_ar and hashtags_en: niche + broad tags without spam.\n"
        "- hashtags: 12-18 total, deduplicated.\n"
        "- keywords: 15-25 search phrases.\n"
        "- upload_tags: 20-30 comma-ready YouTube Studio tags, no hashtags.\n"
        "- thumbnail text must be very short, emotionally clear, and not sensational.\n"
        "- pinned comments should invite respectful engagement.\n"
        "- retention_tips and publish_checklist should be practical and specific.\n"
        "- No markdown, no code fences, no extra text outside JSON.\n\n"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=False)}"
    )

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2200,
            "responseMimeType": "application/json",
        },
    }

    last_error = ""
    for _ in range(max(1, int(max_retries) + 1)):
        try:
            response = requests.post(
                f"{GEMINI_ENDPOINT}?key={api_key}",
                json=body,
                timeout=timeout_sec,
            )
            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            text = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text = parts[0].get("text", "")

            parsed = _extract_json(text)
            return normalize_metadata(parsed), False, ""
        except Exception as exc:
            last_error = str(exc)

    return build_fallback_metadata(context), True, last_error or "Unknown Gemini error"
