#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch 20 images -> Gemini -> Adobe Stock CSV.

Requirements:
  pip install google-generativeai pillow python-dotenv

Env:
  GOOGLE_API_KEY in .env or environment
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import re
import unicodedata
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from PIL import Image

import google.generativeai as genai


# =========================
# CONFIG (easy to edit)
# =========================
DEFAULT_MODEL = "gemini-2.5-flash"  
DEFAULT_BATCH_SIZE = 20

DEFAULT_INPUT_DIR = Path("./zdjecia")
DEFAULT_OUTPUT_CSV = Path("./adobe_dane.csv")

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_OUTPUT_TOKENS = 0

# Reduce vision cost: smaller images => fewer vision tokens
DEFAULT_VISION_MAX_SIDE = 256
DEFAULT_VISION_QUALITY = 25  # JPEG quality (bytes), less effect on tokens than size

KEYWORDS_MIN = 45
# Allowed Adobe Stock categories (must be EXACTLY one of these for each image)
# Allowed Adobe Stock categories in REQUIRED order (1..21)
CATEGORIES: Tuple[str, ...] = (
    "Zwierzęta",
    "Budynki i architektura",
    "Biznes",
    "Napoje",
    "Środowisko",
    "Uczucia i emocje",
    "Jedzenie",
    "Zasoby graficzne",
    "Hobby i rozrywka",
    "Przemysł",
    "Krajobrazy",
    "Styl życia",
    "Ludzie",
    "Rośliny i kwiaty",
    "Religia i kultura",
    "Nauka",
    "Zagadnienia społeczne",
    "Sport",
    "Technologia",
    "Transport",
    "Podróże",
)
CATEGORIES_SET = set(CATEGORIES)
CATEGORY_ID_BY_NAME = {name: i + 1 for i, name in enumerate(CATEGORIES)}
NAME_BY_CATEGORY_ID = {i + 1: name for i, name in enumerate(CATEGORIES)}
def _strip_accents(s: str) -> str:
    # "Środowisko" -> "Srodowisko" (helps match if the model drops diacritics)
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def normalize_category(raw: Any) -> int:
    """
    Returns category ID (1..21) based on:
      - integer ID (1..21),
      - numeric string (e.g. "11"),
      - or category name (case/diacritic-insensitive).
    Returns 0 if cannot be normalized.
    """
    if raw is None:
        return 0

    # If already an int (or float like 11.0)
    if isinstance(raw, (int,)):
        return raw if 1 <= raw <= len(CATEGORIES) else 0
    if isinstance(raw, float) and raw.is_integer():
        i = int(raw)
        return i if 1 <= i <= len(CATEGORIES) else 0

    s = str(raw).strip()
    if not s:
        return 0
    s = re.sub(r"\s+", " ", s)

    # numeric string id
    if re.fullmatch(r"\d{1,2}", s):
        i = int(s)
        return i if 1 <= i <= len(CATEGORIES) else 0

    # Exact match
    if s in CATEGORIES_SET:
        return CATEGORY_ID_BY_NAME[s]

    # Case-insensitive match
    low = s.casefold()
    for c in CATEGORIES:
        if c.casefold() == low:
            return CATEGORY_ID_BY_NAME[c]

    # Accent-insensitive match (only if everything else failed)
    low2 = _strip_accents(s).casefold()
    for c in CATEGORIES:
        if _strip_accents(c).casefold() == low2:
            return CATEGORY_ID_BY_NAME[c]

    return 0

KEYWORDS_MAX = 49

# =========================
# LOGGING
# =========================
logger = logging.getLogger("opis_csv_gemini_batch20")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


# =========================
# PROMPT (your style)
# =========================
SYSTEM_PROMPT = r"""
Jesteś ekspertem SEO ds. fotografii stockowej (Adobe Stock).
Przetwarzasz partię 20 obrazów jednocześnie.

Twoim zadaniem jest przeanalizowanie każdego z 20 obrazów w kolejności, w jakiej zostały przesłane.

Dla KAŻDEGO obrazu wygeneruj obiekt JSON:
1. "index": Numer porządkowy obrazu w przesłanej partii (0-19).
2. "title": Komercyjny, sprzedażowy tytuł (angielski, max 200 znaków).
3. "keywords": String zawierający DOKŁADNIE 45-49 słów kluczowych (angielski), oddzielonych przecinkami.

4. "category": Numer kategorii (1-21) wybrany DOKŁADNIE z tej listy (bez żadnych innych wartości):
   1. Zwierzęta
   2. Budynki i architektura
   3. Biznes
   4. Napoje
   5. Środowisko
   6. Uczucia i emocje
   7. Jedzenie
   8. Zasoby graficzne
   9. Hobby i rozrywka
   10. Przemysł
   11. Krajobrazy
   12. Styl życia
   13. Ludzie
   14. Rośliny i kwiaty
   15. Religia i kultura
   16. Nauka
   17. Zagadnienia społeczne
   18. Sport
   19. Technologia
   20. Transport
   21. Podróże
ZASADY KRYTYCZNE:
- Nie pomiń żadnego zdjęcia. Muszę otrzymać listę dokładnie 20 obiektów.
- Jeśli zdjęcie jest niewyraźne, opisz je najlepiej jak potrafisz, ale nie pomijaj go.
- Styl: Używaj określeń "illustration", "render", "digital composition". Unikaj wprowadzania w błąd, że to "autentyczna fotografia reporterska", choć możesz używać "photorealistic" jako określenia stylu.
- Przestrzegaj limitu słów kluczowych (45-49) dla każdego z 20 zdjęć.
- Output: VALID JSON ONLY (no markdown, no extra text).

Format Outputu:
[
  { "index": 0, "title": "Example commercial title", "keywords": "keyword1, keyword2, keyword3, ...", "category": 12 },
  { "index": 1, "title": "Example commercial title 2", "keywords": "keyword1, keyword2, keyword3, ...", "category": 13 }
]
""".strip()


def build_user_prompt(batch_size: int) -> str:
    return (
        f"Analyze the {batch_size} provided images in EXACT order.\n"
        f"Map output objects by index 0..{batch_size-1} to the same order.\n"
        "Return JSON ONLY.\n"
        "All titles & keywords must be ENGLISH.\n"
    )


# =========================
# HELPERS
# =========================
def ensure_csv_header(path: Path) -> None:
    expected = ["Filename", "Title", "Keywords", "Category", "Releases"]
    if path.exists() and path.stat().st_size > 0:
        # If the file already exists, enforce a consistent header so downstream tools parse correctly.
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                r = csv.reader(f)
                first = next(r, [])
        except Exception:
            first = []
        if first != expected:
            raise ValueError(
                f"Output CSV header mismatch in {path}. Expected {expected} but found {first}. "
                "Use a new --output-csv path or delete the existing file to regenerate it."
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(expected)

def list_images(input_dir: Path) -> List[Path]:
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = [p for p in sorted(input_dir.iterdir()) if p.is_file() and p.suffix.lower() in exts]
    return files


def chunked_exact(paths: List[Path], n: int) -> Tuple[List[List[Path]], List[Path]]:
    full = [paths[i:i+n] for i in range(0, len(paths) - (len(paths) % n), n)]
    rem = paths[len(full)*n:]
    return full, rem


def prepare_image_part(path: Path, max_side: int, quality: int) -> Image.Image:
    """
    Returns a PIL image object resized in-memory.
    NOTE: does NOT write anything back to disk.
    """
    img = Image.open(path)
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    # We keep it as PIL image; Gemini SDK will encode it.
    return img


def strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def parse_json_response(text: str) -> Any:
    t = strip_code_fences(text)
    # Try direct
    try:
        return json.loads(t)
    except Exception:
        # Try to salvage the first JSON array
        m1 = t.find("[")
        m2 = t.rfind("]")
        if m1 != -1 and m2 != -1 and m2 > m1:
            return json.loads(t[m1:m2+1])
        raise


def split_keywords(s: str) -> List[str]:
    parts = [p.strip() for p in s.split(",")]
    parts = [p for p in parts if p]
    return parts


BANNED_PHRASES = (
    "stock keyword",
    "image of",
    "picture of",
)

def clean_keywords(raw: str, title: str) -> str:
    kws = split_keywords(raw)
    out: List[str] = []
    seen = set()

    def ok_kw(k: str) -> bool:
        lk = k.lower()
        if any(bp in lk for bp in BANNED_PHRASES):
            return False
        if re.search(r"\d", lk):
            return False
        if len(lk) < 2:
            return False
        return True

    for k in kws:
        k = re.sub(r"\s+", " ", k).strip()
        lk = k.lower()
        if not ok_kw(k):
            continue
        if lk in seen:
            continue
        seen.add(lk)
        out.append(lk)

    # Enforce range with minimal “generic” padding (from title words first)
    if len(out) < KEYWORDS_MIN:
        title_words = re.findall(r"[A-Za-z]+", title.lower())
        stop = {"the","and","with","in","on","at","a","an","of","to","for","from","during","into","over","under"}
        for w in title_words:
            if w in stop:
                continue
            if w in seen:
                continue
            if re.search(r"\d", w):
                continue
            seen.add(w)
            out.append(w)
            if len(out) >= KEYWORDS_MIN:
                break

    # If still short, add safe stock-ish concepts (last resort)
    fallback_pool = [
        "commercial", "marketing", "advertising", "branding", "copy space",
        "professional", "lifestyle", "creative", "modern", "concept",
        "background", "banner", "template", "design",
    ]
    for w in fallback_pool:
        if len(out) >= KEYWORDS_MIN:
            break
        if w in seen:
            continue
        seen.add(w)
        out.append(w)

    if len(out) > KEYWORDS_MAX:
        out = out[:KEYWORDS_MAX]

    return ", ".join(out)


def sanitize_title(raw: Any) -> str:
    """Return a clean title (<=200 chars) that never contains placeholder '...' and is safe for CSV."""
    t = str(raw or "").strip()
    # remove surrounding quotes
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    # collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()

    # Remove ellipsis-like placeholders anywhere
    t = t.replace("…", " ").replace("...", " ")
    t = re.sub(r"\s+", " ", t).strip()

    # Hard limit (no automatic '...')
    t = t[:200].rstrip()

    # Reject titles that are only punctuation or empty after cleaning
    if not t or re.fullmatch(r"[\W_]+", t):
        return ""
    return t


def validate_items(items: List[Dict[str, Any]], batch_size: int) -> Tuple[bool, str]:
    if len(items) != batch_size:
        return False, f"Expected {batch_size} objects, got {len(items)}"
    idxs = []
    for it in items:
        idx = it.get("index", it.get("filename_index"))
        if idx is None:
            return False, "Missing index/filename_index"
        if not isinstance(idx, int):
            return False, f"Index not int: {idx}"
        idxs.append(idx)
        title = it.get("title", "")
        kw = it.get("keywords", "")
        if not isinstance(title, str):
            return False, f"Bad title for index {idx}"
        title_clean = title.strip()
        # reject placeholders like "..." and titles that are only punctuation
        if (not title_clean) or ("..." in title_clean) or ("…" in title_clean) or re.fullmatch(r"[\W_]+", title_clean):
            return False, f"Bad title for index {idx}"
        if not isinstance(kw, str) or not kw.strip():
            return False, f"Bad keywords for index {idx}"
        category_id = normalize_category(it.get("category", it.get("category_id", "")))
        if not category_id:
            return False, f"Bad category for index {idx}: {it.get('category', '')}"
        it["category"] = category_id
    if sorted(idxs) != list(range(batch_size)):
        return False, f"Indexes mismatch: got {sorted(idxs)}"

    # keyword count check (after splitting by comma)
    for it in items:
        idx = it.get("index", it.get("filename_index"))
        kw_list = split_keywords(it["keywords"])
        if not (KEYWORDS_MIN <= len(kw_list) <= KEYWORDS_MAX):
            return False, f"Keyword count out of range for index {idx}: {len(kw_list)}"

    return True, "ok"


def call_gemini(model_name: str, prompt: str, images: List[Image.Image], temperature: float, max_output_tokens: int | None) -> str:
    model = genai.GenerativeModel(model_name=model_name)
    cfg = {
        "temperature": temperature,
        "response_mime_type": "application/json",
    }
    if max_output_tokens:
        cfg["max_output_tokens"] = int(max_output_tokens)

    resp = model.generate_content([prompt, *images], generation_config=cfg)
    # google-generativeai typically provides resp.text
    return getattr(resp, "text", "") or ""


def call_gemini_text_only(model_name: str, prompt: str, temperature: float, max_output_tokens: int | None) -> str:
    model = genai.GenerativeModel(model_name=model_name)
    cfg = {
        "temperature": temperature,
        "response_mime_type": "application/json",
    }
    if max_output_tokens:
        cfg["max_output_tokens"] = int(max_output_tokens)

    resp = model.generate_content(prompt, generation_config=cfg)
    return getattr(resp, "text", "") or ""


def main() -> int:
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Missing GOOGLE_API_KEY (or GEMINI_API_KEY). Put it in .env or environment.")
        return 2
    genai.configure(api_key=api_key)

    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    ap.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    ap.add_argument("--max-completion-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS,
                    help="Max output tokens. Use 0 to omit the limit (let Gemini decide).")
    ap.add_argument("--vision-max-side", type=int, default=DEFAULT_VISION_MAX_SIDE)
    ap.add_argument("--vision-quality", type=int, default=DEFAULT_VISION_QUALITY)  # kept for symmetry (unused in PIL path)
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output_csv = Path(args.output_csv)
    batch_size = args.batch_size

    files = list_images(input_dir)
    if not files:
        logger.warning(f"No images found in {input_dir}")
        return 0

    batches, rem = chunked_exact(files, batch_size)
    if rem:
        logger.warning(f"Found {len(rem)} leftover file(s) that don't form a full batch of {batch_size}; skipping them: "
                       + ", ".join(p.name for p in rem))

    ensure_csv_header(output_csv)
    logger.info(
        f"Processing {len(batches)} batches ({batch_size} images each). "
        f"model={args.model} | vision_max_side={args.vision_max_side} | max_output_tokens={args.max_completion_tokens}"
    )

    ok_batches = 0
    failed_batches = 0

    for bi, batch in enumerate(batches, start=1):
        filenames = [p.name for p in batch]
        images = [prepare_image_part(p, args.vision_max_side, args.vision_quality) for p in batch]

        full_prompt = SYSTEM_PROMPT + "\n\n" + build_user_prompt(batch_size)

        # Basic backoff loop for 429 / transient
        last_err = None
        for attempt in range(1, 6):
            try:
                text = call_gemini(
                    model_name=args.model,
                    prompt=full_prompt,
                    images=images,
                    temperature=args.temperature,
                    max_output_tokens=(None if args.max_completion_tokens == 0 else args.max_completion_tokens),
                )
                data = parse_json_response(text)
                if not isinstance(data, list):
                    raise ValueError("Response is not a JSON list")

                # normalize keys + clean keywords
                items: List[Dict[str, Any]] = []
                for it in data:
                    if not isinstance(it, dict):
                        continue
                    idx = it.get("index", it.get("filename_index"))
                    title = it.get("title", "")
                    keywords = it.get("keywords", "")
                    if isinstance(idx, int):
                        title_s = sanitize_title(title)
                        kw_s = clean_keywords(str(keywords), title_s)
                        cat_s = normalize_category(it.get("category", it.get("category_id", "")))
                        items.append({"index": idx, "title": title_s, "keywords": kw_s, "category": cat_s})

                # reorder by index
                items.sort(key=lambda x: x["index"])

                valid, reason = validate_items(items, batch_size)
                if not valid:
                    # one text-only repair (cheaper than resending images)
                    repair_prompt = (
                        SYSTEM_PROMPT
                        + "\n\nYou previously returned JSON that violates constraints.\n"
                        + f"Fix it so it is a JSON list of exactly {batch_size} objects with indexes 0..{batch_size-1}.\n"
                        + "Keep titles as-is unless missing. Fix keywords so each has 45-49 comma-separated ENGLISH keywords.\n"
                        + "Ensure each object contains \"category\" as an integer 1-21 (category ID), where: 1=Zwierzęta; 2=Budynki i architektura; 3=Biznes; 4=Napoje; 5=Środowisko; 6=Uczucia i emocje; 7=Jedzenie; 8=Zasoby graficzne; 9=Hobby i rozrywka; 10=Przemysł; 11=Krajobrazy; 12=Styl życia; 13=Ludzie; 14=Rośliny i kwiaty; 15=Religia i kultura; 16=Nauka; 17=Zagadnienia społeczne; 18=Sport; 19=Technologia; 20=Transport; 21=Podróże.\n"

                        + "Remove any digits and banned filler phrases.\n"
                        + "Return JSON only.\n\n"
                        + "BROKEN_JSON:\n"
                        + json.dumps(items, ensure_ascii=False)
                    )
                    repaired_text = call_gemini_text_only(
                        model_name=args.model,
                        prompt=repair_prompt,
                        temperature=0.0,
                        max_output_tokens=(None if args.max_completion_tokens == 0 else args.max_completion_tokens),
                    )
                    repaired = parse_json_response(repaired_text)
                    if isinstance(repaired, list):
                        items2: List[Dict[str, Any]] = []
                        for it in repaired:
                            if not isinstance(it, dict):
                                continue
                            idx = it.get("index", it.get("filename_index"))
                            title = it.get("title", "")
                            keywords = it.get("keywords", "")
                            if isinstance(idx, int):
                                title_s = sanitize_title(title)
                                kw_s = clean_keywords(str(keywords), title_s)
                                cat_s = normalize_category(it.get("category", it.get("category_id", "")))
                                items2.append({"index": idx, "title": title_s, "keywords": kw_s, "category": cat_s})
                        items2.sort(key=lambda x: x["index"])
                        valid2, reason2 = validate_items(items2, batch_size)
                        if not valid2:
                            raise ValueError(f"Validation failed after repair: {reason2}")
                        items = items2
                    else:
                        raise ValueError(f"Repair did not return a JSON list (original issue: {reason})")

                # write CSV rows
                rows = []
                for i, it in enumerate(items):
                    fn = filenames[i]  # after sorting indexes this should match 0..N-1
                    rows.append((fn, it["title"], it["keywords"], it.get("category",""), ""))

                with open(output_csv, "a", encoding="utf-8", newline="") as f:
                    w = csv.writer(f, lineterminator="\n")
                    w.writerows(rows)

                ok_batches += 1
                logger.info(f"Batch {bi}/{len(batches)} OK: {filenames[0]} ...")
                break

            except Exception as e:
                last_err = e
                msg = str(e)
                # crude 429 detection (google-generativeai raises different exception types depending on version)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    # respect server hint if present
                    m = re.search(r"Please retry in\\s*([0-9.]+)s", msg)
                    sleep_s = float(m.group(1)) if m else min(8.0, 1.5 * attempt)
                    logger.warning(f"Batch {bi} Gemini 429/quota (attempt {attempt}/5): sleeping {sleep_s:.2f}s")
                    time.sleep(sleep_s)
                    continue

                logger.warning(f"Batch {bi} failed (attempt {attempt}/5): {e}")
                time.sleep(min(8.0, 0.8 * attempt))

        else:
            failed_batches += 1
            logger.error(f"❌ Batch {bi} failed permanently. Example file: {filenames[0]} | last_err={last_err}")

    logger.info(f"Done. Successful batches={ok_batches}, failed batches={failed_batches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
