"""
logo_fetcher.py – Automatic logo download with quality validation and local cache.

Search order
------------
1. Local cache (skip download if a valid cached file exists)
2. English Wikipedia / Wikimedia (SVG preferred, PNG fallback)
3. Spanish Wikipedia / Wikimedia (same preference)
4. TheSportsDB free endpoint (PNG)

Quality rules
-------------
- Raster (PNG/JPG): min(width, height) >= 400 px
- SVG:              renders cleanly at 1024×1024 via cairosvg

Logo status values returned
---------------------------
  OK_WIKI_SVG      – valid SVG from Wikipedia
  OK_WIKI_PNG      – valid PNG from Wikipedia (≥ 400 px)
  OK_SPORTSDB_PNG  – valid PNG from TheSportsDB (≥ 400 px)
  MANUAL_OK        – set externally by manual selection
  LOW_QUALITY_WIKI     – PNG from Wikipedia but < 400 px
  LOW_QUALITY_SPORTSDB – PNG from SportsDB but < 400 px
  NOT_FOUND        – no source produced a result
  ERROR            – unexpected exception
"""

import io
import json
import os
from datetime import datetime

import requests
from PIL import Image

from normalizer import get_search_candidates, slugify

try:
    import cairosvg
    _CAIROSVG = True
except Exception:
    _CAIROSVG = False

# ── Constants ──────────────────────────────────────────────────────────────────

MIN_RASTER_PX = 400          # minimum side for a raster logo
SVG_RENDER_PX = 1024         # resolution used to validate SVG logos

_HEADERS = {
    'User-Agent': (
        'SIBA-BatchGenerator/1.0 '
        '(https://github.com/EleNanoAsterix/ENFRENTAMIENTOS_SIBA; '
        'contact via GitHub issues)'
    )
}

# Image filenames containing any of these words are treated as logo candidates.
_LOGO_KEYWORDS = frozenset({
    'logo', 'crest', 'badge', 'shield', 'escudo', 'emblem',
    'wappen', 'stemma', 'blason', 'armoiries', 'blazon',
})

# Image filenames containing any of these words are NOT logos.
_SKIP_KEYWORDS = frozenset({
    'stadium', 'ground', 'player', 'manager', 'coach',
    'shirt', 'jersey', 'kit', 'home', 'away', 'third',
    'flag', 'map', 'location', 'signature', 'portrait',
})

_SPORTSDB_URL = 'https://www.thesportsdb.com/api/v1/json/3/searchteams.php'

_REQUEST_TIMEOUT = 20  # seconds


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_logo(team_name, country, cache_dir, timeout=_REQUEST_TIMEOUT):
    """Return ``(local_path, status, source_url, size_tuple)`` for *team_name*.

    *cache_dir* is the root cache directory (sub-dirs ``wiki/``, ``sportsdb/``,
    ``manual/`` are created automatically).

    On failure ``local_path`` is ``None``; *status* is ``NOT_FOUND`` or
    ``ERROR``.
    """
    slug = slugify(team_name)
    candidates = get_search_candidates(team_name, country)

    # 1. Local cache
    cached = _find_cached(slug, cache_dir)
    if cached[0]:
        return cached

    # 2. Wikipedia (English then Spanish)
    for lang in ('en', 'es'):
        result = _fetch_wikipedia(candidates, slug, cache_dir, lang, timeout)
        if result[0]:
            return result

    # 3. TheSportsDB
    result = _fetch_sportsdb(candidates, slug, cache_dir, timeout)
    if result[0]:
        return result

    return None, 'NOT_FOUND', None, None


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _find_cached(slug, cache_dir):
    for source in ('wiki', 'sportsdb', 'manual'):
        for ext in ('svg', 'png', 'jpg', 'jpeg'):
            path = os.path.join(cache_dir, source, f"{slug}.{ext}")
            meta_path = path + '.json'
            if os.path.isfile(path) and os.path.isfile(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as fh:
                        meta = json.load(fh)
                    size = meta.get('size')
                    if isinstance(size, list):
                        size = tuple(size)
                    return path, meta.get('status', 'CACHED'), meta.get('url'), size
                except Exception:
                    pass
    return None, None, None, None


def _save_meta(image_path, status, url, source, size):
    meta = {
        'status': status,
        'url': url,
        'source': source,
        'size': list(size) if size else None,
        'downloaded_at': datetime.now().isoformat(),
    }
    with open(image_path + '.json', 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, indent=2)


# ── Wikipedia / Wikimedia ──────────────────────────────────────────────────────

def _fetch_wikipedia(candidates, slug, cache_dir, lang, timeout):
    wiki_api = f"https://{lang}.wikipedia.org/w/api.php"
    for candidate in candidates:
        page_title = _wiki_search(candidate, wiki_api, timeout)
        if not page_title:
            continue

        image_titles = _wiki_page_images(page_title, wiki_api, timeout)
        logo_titles = _filter_logo_images(image_titles)
        if not logo_titles:
            continue

        for file_title in logo_titles:
            result = _wiki_download_image(file_title, slug, cache_dir, wiki_api, timeout)
            if result[0]:
                return result
    return None, None, None, None


def _wiki_search(query, wiki_api, timeout):
    """Search Wikipedia and return the title of the best-matching page."""
    try:
        resp = requests.get(
            wiki_api,
            params={
                'action': 'query',
                'list': 'search',
                'srsearch': query,
                'srlimit': 3,
                'srnamespace': 0,
                'format': 'json',
            },
            headers=_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        results = resp.json().get('query', {}).get('search', [])
        if results:
            return results[0]['title']
    except Exception:
        pass
    return None


def _wiki_page_images(page_title, wiki_api, timeout):
    """Return a list of image file-titles found on a Wikipedia page."""
    try:
        resp = requests.get(
            wiki_api,
            params={
                'action': 'query',
                'titles': page_title,
                'prop': 'images',
                'imlimit': 50,
                'format': 'json',
            },
            headers=_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        pages = resp.json().get('query', {}).get('pages', {})
        for page in pages.values():
            return [img['title'] for img in page.get('images', [])]
    except Exception:
        pass
    return []


def _filter_logo_images(image_titles):
    """Filter *image_titles* to likely-logo files; SVGs first, then PNGs."""
    svgs, pngs = [], []
    for title in image_titles:
        lower = title.lower()
        if any(kw in lower for kw in _SKIP_KEYWORDS):
            continue
        if not any(kw in lower for kw in _LOGO_KEYWORDS):
            continue
        if lower.endswith('.svg'):
            svgs.append(title)
        elif lower.endswith('.png') or lower.endswith('.jpg') or lower.endswith('.jpeg'):
            pngs.append(title)
    return svgs + pngs


def _wiki_download_image(file_title, slug, cache_dir, wiki_api, timeout):
    """Download a single Wikimedia file and validate its quality."""
    try:
        resp = requests.get(
            wiki_api,
            params={
                'action': 'query',
                'titles': file_title,
                'prop': 'imageinfo',
                'iiprop': 'url|size|mime',
                'format': 'json',
            },
            headers=_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        pages = resp.json().get('query', {}).get('pages', {})

        image_url = None
        mime_type = ''
        for page in pages.values():
            info = page.get('imageinfo', [])
            if info:
                image_url = info[0].get('url')
                mime_type = info[0].get('mime', '')
                break

        if not image_url:
            return None, None, None, None

        is_svg = 'svg' in mime_type or image_url.lower().split('?')[0].endswith('.svg')
        ext = 'svg' if is_svg else 'png'
        dest = os.path.join(cache_dir, 'wiki', f"{slug}.{ext}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        _download_file(image_url, dest, timeout)

        valid, size = _validate_image(dest, is_svg)
        if not valid:
            _safe_remove(dest)
            return None, None, None, None

        status = f"OK_WIKI_{'SVG' if is_svg else 'PNG'}"
        if not is_svg and size and min(size) < MIN_RASTER_PX:
            status = 'LOW_QUALITY_WIKI'

        _save_meta(dest, status, image_url, 'wiki', size)
        return dest, status, image_url, size

    except Exception:
        return None, None, None, None


# ── TheSportsDB ────────────────────────────────────────────────────────────────

def _fetch_sportsdb(candidates, slug, cache_dir, timeout):
    for candidate in candidates:
        try:
            resp = requests.get(
                _SPORTSDB_URL,
                params={'t': candidate},
                headers=_HEADERS,
                timeout=timeout,
            )
            resp.raise_for_status()
            teams = resp.json().get('teams')
            if not teams:
                continue

            badge_url = teams[0].get('strTeamBadge') or teams[0].get('strTeamLogo')
            if not badge_url:
                continue

            dest = os.path.join(cache_dir, 'sportsdb', f"{slug}.png")
            os.makedirs(os.path.dirname(dest), exist_ok=True)

            _download_file(badge_url, dest, timeout)

            valid, size = _validate_image(dest, False)
            if not valid:
                _safe_remove(dest)
                continue

            status = 'OK_SPORTSDB_PNG'
            if size and min(size) < MIN_RASTER_PX:
                status = 'LOW_QUALITY_SPORTSDB'

            _save_meta(dest, status, badge_url, 'sportsdb', size)
            return dest, status, badge_url, size

        except requests.RequestException:
            # Network error – TheSportsDB not accessible; stop trying
            break
        except Exception:
            continue

    return None, 'NOT_FOUND', None, None


# ── Download / validate helpers ────────────────────────────────────────────────

def _download_file(url, dest_path, timeout):
    resp = requests.get(url, headers=_HEADERS, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(dest_path, 'wb') as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            fh.write(chunk)


def _validate_image(path, is_svg):
    """Return ``(is_valid, (width, height))``."""
    try:
        if is_svg:
            if not _CAIROSVG:
                # Cannot validate without cairosvg – assume OK
                return True, (SVG_RENDER_PX, SVG_RENDER_PX)
            png_data = cairosvg.svg2png(
                url=path,
                output_width=SVG_RENDER_PX,
                output_height=SVG_RENDER_PX,
            )
            img = Image.open(io.BytesIO(png_data))
            # Reject blank/empty renders
            extrema = img.convert('L').getextrema()
            if extrema[0] == extrema[1]:
                return False, None
            return True, (img.width, img.height)
        else:
            img = Image.open(path)
            return True, img.size
    except Exception:
        return False, None


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
