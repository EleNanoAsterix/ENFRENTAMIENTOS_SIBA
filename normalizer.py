"""
normalizer.py
Normaliza nombres de equipos y genera variantes de búsqueda.
"""

import re
import unicodedata


# Sufijos comunes en nombres de clubes de fútbol
_SUFFIXES = [
    "AFC", "A.F.C.", "FC", "F.C.", "CF", "C.F.", "AC", "A.C.",
    "SC", "S.C.", "CD", "C.D.", "SD", "S.D.", "UD", "U.D.",
    "RC", "R.C.", "RCD", "R.C.D.", "SL", "S.L.", "CA", "C.A.",
    "FK", "SK", "NK", "GD", "AD", "AS",
]

_PREFIXES = [
    "Club", "Club Atlético", "Club Deportivo", "Deportivo",
    "Atlético", "Atlético de", "Real", "Athletic",
    "Sporting", "Unión", "Union",
]

# Normalize dots in abbreviations: A.F.C. → AFC, F.C. → FC
# No \b after the final dot because '.' is not a word character
_DOTTED_ABBREV_3CHAR = re.compile(r'\b([A-Z])\.([A-Z])\.([A-Z])\.(?=\s|$)')
_DOTTED_ABBREV_2CHAR = re.compile(r'\b([A-Z])\.([A-Z])\.(?=\s|$)')


def remove_accents(text: str) -> str:
    """Quita diacríticos (tildes, ñ→n, etc.)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def slugify(text: str) -> str:
    """Devuelve un slug seguro para nombres de archivo/carpeta."""
    text = remove_accents(text)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text


def _collapse(text: str) -> str:
    """Trim + colapsar espacios dobles."""
    return re.sub(r"\s+", " ", text.strip())


def _normalize_dots(text: str) -> str:
    """Converts A.F.C. → AFC, F.C. → FC, etc."""
    text = _DOTTED_ABBREV_3CHAR.sub(lambda m: m.group(1) + m.group(2) + m.group(3), text)
    text = _DOTTED_ABBREV_2CHAR.sub(lambda m: m.group(1) + m.group(2), text)
    return text


def display_name(raw: str) -> str:
    """Versión 'limpia' para mostrar (solo trim + normalizar espacios)."""
    return _collapse(raw)


def _strip_suffix(name: str) -> str | None:
    """
    Intenta quitar el sufijo al final del nombre.
    Retorna el nombre sin sufijo o None si no se encontró.
    """
    name = _normalize_dots(name)
    for suf in sorted(_SUFFIXES, key=len, reverse=True):
        pattern = re.compile(
            r"(\s*,?\s*" + re.escape(suf) + r")\s*$", re.IGNORECASE
        )
        stripped = pattern.sub("", name).strip()
        if stripped and stripped != name:
            return stripped
    return None


def _strip_prefix(name: str) -> str | None:
    """Intenta quitar el prefijo al inicio del nombre."""
    for pre in sorted(_PREFIXES, key=len, reverse=True):
        pattern = re.compile(
            r"^" + re.escape(pre) + r"\s+", re.IGNORECASE
        )
        stripped = pattern.sub("", name).strip()
        if stripped and stripped != name:
            return stripped
    return None


def search_candidates(raw: str) -> list[str]:
    """
    Devuelve una lista de variantes de búsqueda para el nombre dado,
    de más específico a más flexible (sin duplicados, conservando orden).
    """
    name = _collapse(raw)
    name_nodots = _normalize_dots(name)

    seen: set[str] = set()
    result: list[str] = []

    def add(s: str) -> None:
        s = _collapse(s)
        if s and s not in seen:
            seen.add(s)
            result.append(s)

    # 1. Nombre original (limpio)
    add(name)
    # 2. Nombre con puntos normalizados
    add(name_nodots)
    # 3. Sin diacríticos
    add(remove_accents(name_nodots))

    # 4. Sin sufijo
    stripped_suf = _strip_suffix(name_nodots)
    if stripped_suf:
        add(stripped_suf)
        add(remove_accents(stripped_suf))

    # 5. Sin prefijo
    stripped_pre = _strip_prefix(name_nodots)
    if stripped_pre:
        add(stripped_pre)
        add(remove_accents(stripped_pre))

    # 6. Sin prefijo Y sin sufijo
    if stripped_suf:
        sp2 = _strip_prefix(stripped_suf)
        if sp2:
            add(sp2)
            add(remove_accents(sp2))

    # 7. Variante con prefijo quitado desde nombre original sin sufijo
    if stripped_pre:
        sp2 = _strip_suffix(stripped_pre)
        if sp2:
            add(sp2)
            add(remove_accents(sp2))

    return result
