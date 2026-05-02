"""
logo_fetcher.py
Busca y descarga logos de equipos desde Wikipedia/Wikimedia y TheSportsDB.
Cachea resultados localmente. Valida calidad mínima 400x400.
"""

import json
import re
import time
import urllib.parse
from pathlib import Path

import requests
from PIL import Image

from normalizer import search_candidates, slugify, remove_accents

# ── Configuración ──────────────────────────────────────────────────────────────
CACHE_DIR = Path("cache/logos")
MIN_SIZE = 400          # mínimo por dimensión para imágenes raster
SVG_RENDER_SIZE = 1024  # tamaño de renderizado para validación de SVG

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "ENFRENTAMIENTOS_SIBA/1.0 "
            "(https://github.com/EleNanoAsterix/ENFRENTAMIENTOS_SIBA; "
            "contact via github) "
            "requests/python"
        )
    }
)

# TheSportsDB free/public key ("3" is the publicly documented free-tier key,
# intentionally not a secret — see https://www.thesportsdb.com/api.php)
_SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

# Wikipedia API endpoint (any language)
_WIKI_API = "https://{lang}.wikipedia.org/w/api.php"

# Supported image extensions
_IMG_EXTS = {".svg", ".png", ".jpg", ".jpeg", ".webp"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 15, stream: bool = False, **kwargs):
    """Wrapper GET con reintentos básicos."""
    for attempt in range(3):
        try:
            r = _SESSION.get(url, timeout=timeout, stream=stream, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    return None  # unreachable


def _cache_path(source: str, country: str, team: str, ext: str) -> Path:
    country_slug = slugify(country) if country else "_sin_pais"
    team_slug = slugify(team)
    return CACHE_DIR / source / country_slug / f"{team_slug}{ext}"


def _meta_path(logo_path: Path) -> Path:
    return logo_path.with_suffix(".json")


def _load_meta(logo_path: Path) -> dict | None:
    mp = _meta_path(logo_path)
    if mp.exists():
        try:
            return json.loads(mp.read_text("utf-8"))
        except Exception:
            return None
    return None


def _save_meta(logo_path: Path, meta: dict) -> None:
    mp = _meta_path(logo_path)
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")


def _validate_image(path: Path) -> tuple[bool, str, tuple[int, int]]:
    """
    Valida el archivo descargado.
    Retorna (ok, status_code, (w, h))
    status_code: OK_SVG | OK_PNG | LOW_QUALITY | ERROR
    """
    if path.suffix.lower() == ".svg":
        # Renderizar SVG a PNG temporal para verificar
        try:
            import cairosvg
            import io
            svg_data = path.read_bytes()
            png_data = cairosvg.svg2png(
                bytestring=svg_data,
                output_width=SVG_RENDER_SIZE,
                output_height=SVG_RENDER_SIZE,
            )
            img = Image.open(io.BytesIO(png_data))
            w, h = img.size
            return True, "OK_SVG", (w, h)
        except Exception as e:
            return False, f"ERROR_SVG_RENDER:{e}", (0, 0)
    else:
        try:
            img = Image.open(path)
            w, h = img.size
            if min(w, h) >= MIN_SIZE:
                return True, "OK_PNG", (w, h)
            else:
                return False, f"LOW_QUALITY_{min(w,h)}px", (w, h)
        except Exception as e:
            return False, f"ERROR_OPEN:{e}", (0, 0)


# ── Wikipedia / Wikimedia ──────────────────────────────────────────────────────

def _wiki_search_page(query: str, lang: str = "es") -> str | None:
    """
    Busca la página de Wikipedia más relevante para `query`.
    Retorna el título de la página o None.
    """
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 3,
        "format": "json",
        "utf8": 1,
    }
    try:
        r = _get(_WIKI_API.format(lang=lang), params=params, timeout=10)
        data = r.json()
        results = data.get("query", {}).get("search", [])
        if results:
            return results[0]["title"]
    except Exception:
        pass
    return None


def _wiki_page_images(title: str, lang: str = "es") -> list[str]:
    """
    Extrae los nombres de archivos de imagen del wikitext de la página
    (buscando en infobox: logo, escudo, crest, badge, image).
    Retorna lista de nombres de archivo (sin el prefijo File:/Archivo:).
    """
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
        "utf8": 1,
    }
    try:
        r = _get(_WIKI_API.format(lang=lang), params=params, timeout=12)
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for page_data in pages.values():
            content = (
                page_data.get("revisions", [{}])[0]
                .get("slots", {})
                .get("main", {})
                .get("*", "")
            )
            if not content:
                # Try alternate key structure
                content = (
                    page_data.get("revisions", [{}])[0]
                    .get("*", "")
                )
            if content:
                return _extract_logo_from_wikitext(content)
    except Exception:
        pass
    return []


def _extract_logo_from_wikitext(wikitext: str) -> list[str]:
    """
    Extrae nombres de archivo de logos/escudos del wikitext de la infobox.
    Prioriza SVG.
    """
    # Claves de infobox que suelen contener el logo/escudo
    logo_keys = [
        "logo", "escudo", "crest", "badge", "image",
        "imagen", "image_name", "logo_club",
        "current_logo", "team_logo", "LogoA", "LogoB",
    ]
    pattern = re.compile(
        r"\|\s*(?:" + "|".join(re.escape(k) for k in logo_keys) + r")\s*=\s*"
        r"\[?\[?(?:(?:File|Archivo|Image|Imagen|Fichier|Datei|Bestand|Fil):\s*)?"
        r"([^\|\]\n\{\}]+\.(?:svg|png|jpg|jpeg|webp))",
        re.IGNORECASE,
    )
    matches = pattern.findall(wikitext)
    filenames: list[str] = []
    for m in matches:
        fname = m.strip().strip("[]").strip()
        if fname:
            filenames.append(fname)

    # Priorizar SVG
    svgs = [f for f in filenames if f.lower().endswith(".svg")]
    others = [f for f in filenames if not f.lower().endswith(".svg")]
    return svgs + others


def _wikimedia_file_url(filename: str) -> str | None:
    """
    Resuelve el URL de descarga directo de un archivo en Wikimedia Commons.
    """
    # Normalizar nombre de archivo
    fname = filename.strip().replace(" ", "_")
    # Quitar prefijos tipo "File:", "Archivo:", etc.
    fname = re.sub(
        r"^(?:File|Archivo|Image|Imagen|Fichier|Datei|Bestand|Fil):\s*",
        "",
        fname,
        flags=re.IGNORECASE,
    ).strip().replace(" ", "_")

    params = {
        "action": "query",
        "titles": f"File:{fname}",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
        "utf8": 1,
    }
    try:
        r = _get(
            "https://commons.wikimedia.org/w/api.php",
            params=params,
            timeout=10,
        )
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for page_data in pages.values():
            info = page_data.get("imageinfo", [])
            if info:
                return info[0].get("url")
    except Exception:
        pass
    return None


def _fetch_wiki_logo(
    team: str, country: str = ""
) -> tuple[bytes | None, str, str]:
    """
    Intenta descargar logo de Wikipedia/Wikimedia.
    Retorna (data, ext, origin_url) o (None, '', '')
    """
    candidates = search_candidates(team)
    # Agregar variantes con país
    if country:
        country_clean = remove_accents(country.strip())
        extra = [f"{c} {country_clean}" for c in candidates[:3]]
        extra += [f"{c} ({country_clean})" for c in candidates[:3]]
        candidates = extra + candidates

    for lang in ("es", "en", "pt", "fr", "de"):
        for query in candidates:
            title = _wiki_search_page(query, lang=lang)
            if not title:
                continue
            filenames = _wiki_page_images(title, lang=lang)
            for fname in filenames:
                url = _wikimedia_file_url(fname)
                if not url:
                    continue
                ext = Path(url.split("?")[0]).suffix.lower()
                if ext not in _IMG_EXTS:
                    ext = ".png"
                try:
                    r = _get(url, timeout=20, stream=True)
                    data = r.content
                    if data:
                        return data, ext, url
                except Exception:
                    continue
    return None, "", ""


# ── TheSportsDB ────────────────────────────────────────────────────────────────

def _fetch_sportsdb_logo(team: str) -> tuple[bytes | None, str, str]:
    """
    Busca logo en TheSportsDB (free tier, key=3).
    Retorna (data, ext, origin_url) o (None, '', '')
    """
    candidates = search_candidates(team)
    for query in candidates:
        url = f"{_SPORTSDB_BASE}/searchteams.php"
        try:
            r = _get(url, params={"t": query}, timeout=10)
            data = r.json()
            teams_list = data.get("teams") or []
            for t in teams_list:
                badge_url = t.get("strTeamBadge") or t.get("strTeamLogo") or ""
                if not badge_url:
                    continue
                # Añadir /preview para obtener imagen de mayor tamaño
                badge_url_hq = badge_url
                if badge_url_hq and not badge_url_hq.endswith("/preview"):
                    badge_url_hq = badge_url_hq + "/preview"
                for burl in [badge_url_hq, badge_url]:
                    try:
                        img_r = _get(burl, timeout=15, stream=True)
                        ext = Path(burl.split("?")[0]).suffix.lower()
                        if ext not in _IMG_EXTS:
                            ext = ".png"
                        img_data = img_r.content
                        if img_data:
                            return img_data, ext, burl
                    except Exception:
                        continue
        except Exception:
            continue
    return None, "", ""


# ── API pública ────────────────────────────────────────────────────────────────

class LogoResult:
    __slots__ = (
        "path", "status", "source", "ext", "origin_url",
        "validated_size", "error",
    )

    def __init__(self):
        self.path: Path | None = None
        self.status: str = "NOT_FOUND"
        self.source: str = ""
        self.ext: str = ""
        self.origin_url: str = ""
        self.validated_size: tuple[int, int] = (0, 0)
        self.error: str = ""

    def to_dict(self) -> dict:
        return {
            "path": str(self.path) if self.path else "",
            "status": self.status,
            "source": self.source,
            "ext": self.ext,
            "origin_url": self.origin_url,
            "validated_size": self.validated_size,
            "error": self.error,
        }


def fetch_logo(
    team: str,
    country: str = "",
    force_refresh: bool = False,
    progress_callback=None,
) -> LogoResult:
    """
    Descarga/carga desde caché el logo de un equipo.

    Orden:
      1. Caché local (si ya existe y es válido)
      2. Wikipedia/Wikimedia
      3. TheSportsDB

    Retorna un LogoResult con path, status, source, etc.
    """
    result = LogoResult()

    def _cb(msg: str):
        if progress_callback:
            progress_callback(msg)

    # ── 1. Verificar caché ──────────────────────────────────────────────
    if not force_refresh:
        for source in ("wiki", "sportsdb", "manual"):
            for ext in (".svg", ".png", ".jpg", ".jpeg"):
                cp = _cache_path(source, country, team, ext)
                if cp.exists():
                    meta = _load_meta(cp)
                    if meta:
                        result.path = cp
                        result.status = meta.get("status", "CACHED")
                        result.source = meta.get("source", source)
                        result.ext = ext
                        result.origin_url = meta.get("origin_url", "")
                        result.validated_size = tuple(
                            meta.get("validated_size", [0, 0])
                        )
                        _cb(f"[CACHE] {team}: {result.status}")
                        return result

    # ── 2. Wikipedia/Wikimedia ──────────────────────────────────────────
    _cb(f"[WIKI] Buscando {team}…")
    try:
        data, ext, origin_url = _fetch_wiki_logo(team, country)
    except Exception as e:
        data, ext, origin_url = None, "", ""
        result.error += f"Wiki error: {e}; "

    if data:
        cp = _cache_path("wiki", country, team, ext)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_bytes(data)
        ok, status_code, size = _validate_image(cp)
        source_label = "wiki"
        meta = {
            "status": status_code,
            "source": source_label,
            "origin_url": origin_url,
            "validated_size": list(size),
        }
        _save_meta(cp, meta)
        result.path = cp
        result.status = status_code
        result.source = source_label
        result.ext = ext
        result.origin_url = origin_url
        result.validated_size = size
        _cb(f"[WIKI] {team}: {status_code} {size}")
        if ok:
            return result
        # LOW_QUALITY: seguimos buscando mejor fuente pero no lanzamos error

    # ── 3. TheSportsDB ──────────────────────────────────────────────────
    _cb(f"[SPORTSDB] Buscando {team}…")
    sdb_data, sdb_ext, sdb_url = None, "", ""
    try:
        sdb_data, sdb_ext, sdb_url = _fetch_sportsdb_logo(team)
    except Exception as e:
        result.error += f"SportsDB error: {e}; "

    if sdb_data:
        cp2 = _cache_path("sportsdb", country, team, sdb_ext)
        cp2.parent.mkdir(parents=True, exist_ok=True)
        cp2.write_bytes(sdb_data)
        ok2, status_code2, size2 = _validate_image(cp2)
        meta2 = {
            "status": status_code2,
            "source": "sportsdb",
            "origin_url": sdb_url,
            "validated_size": list(size2),
        }
        _save_meta(cp2, meta2)
        # Usar sportsdb si es mejor calidad que wiki
        if ok2 or not result.path:
            result.path = cp2
            result.status = status_code2
            result.source = "sportsdb"
            result.ext = sdb_ext
            result.origin_url = sdb_url
            result.validated_size = size2
        _cb(f"[SPORTSDB] {team}: {status_code2} {size2}")
        if ok2:
            return result

    # ── 4. No encontrado ────────────────────────────────────────────────
    if not result.path:
        result.status = "NOT_FOUND"
        _cb(f"[NOT_FOUND] {team}")

    return result


def set_manual_logo(
    team: str,
    country: str,
    src_path: str | Path,
) -> LogoResult:
    """
    Copia un logo elegido manualmente al caché y lo valida.
    """
    src = Path(src_path)
    ext = src.suffix.lower()
    if ext not in _IMG_EXTS:
        ext = ".png"

    cp = _cache_path("manual", country, team, ext)
    cp.parent.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.copy2(src, cp)

    ok, status_code, size = _validate_image(cp)
    meta = {
        "status": "MANUAL_OK" if ok else status_code,
        "source": "manual",
        "origin_url": str(src),
        "validated_size": list(size),
    }
    _save_meta(cp, meta)

    result = LogoResult()
    result.path = cp
    result.status = "MANUAL_OK" if ok else status_code
    result.source = "manual"
    result.ext = ext
    result.origin_url = str(src)
    result.validated_size = size
    return result
