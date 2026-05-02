"""
normalizer.py – Team name normalization and search-candidate generation.

Handles:
- Stripping accent marks (for filesystem-safe slugs and search queries)
- Title-casing ALL-CAPS names coming from Excel
- Generating ordered lists of search variants (with/without suffixes,
  with/without accents, with country qualification)
"""

import re
import unicodedata

# Common team-name suffixes that can be stripped to produce a base name.
# Stored lowercased and without dots for easy comparison.
_SUFFIXES = frozenset({
    'fc', 'cf', 'ac', 'sc', 'cd', 'ud', 'sd', 'bc',
    'afc', 'rfc', 'sfc', 'bsc', 'fk', 'sk',
    'utd', 'united', 'city',
    'if', 'ik', 'bk',
})

# Common first-word prefixes that can be stripped to produce a shorter name.
_PREFIXES = frozenset({
    'club', 'atletico', 'deportivo', 'sporting',
    'real', 'asociacion', 'sociedad',
    'calcio', 'football',
})


def strip_accents(text):
    """Remove accent marks (diacritics) from *text*."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def normalize_display(name):
    """Return a clean display name.

    - Collapses multiple spaces / leading-trailing whitespace.
    - Converts ALL-CAPS strings to Title Case.
    """
    name = ' '.join(name.strip().split())
    if name.isupper():
        name = name.title()
    return name


def get_search_candidates(name, country=None):
    """Return an ordered list of search-query candidates for *name*.

    The list runs from the most specific variant to the most flexible one,
    so callers should try them in order and stop at the first hit.

    Args:
        name:    raw team name as it appears in the Excel file.
        country: optional country string (used as a disambiguation suffix).

    Returns:
        list[str] – deduplicated, ordered candidate strings.
    """
    name = normalize_display(name)
    seen = set()
    candidates = []

    def _add(s):
        s = ' '.join(s.strip().split())
        if s and s not in seen:
            seen.add(s)
            candidates.append(s)

    _add(name)

    no_accent = strip_accents(name)
    _add(no_accent)

    parts = name.split()

    # Variant: remove trailing suffix word (e.g. "Arsenal FC" → "Arsenal")
    if len(parts) > 1:
        last = parts[-1].lower().rstrip('.')
        last_plain = last.replace('.', '')
        if last in _SUFFIXES or last_plain in _SUFFIXES:
            base = ' '.join(parts[:-1])
            _add(base)
            _add(strip_accents(base))

    # Variant: remove leading prefix word (e.g. "Club Atlético Tucumán" → "Atlético Tucumán")
    if len(parts) > 1:
        first = strip_accents(parts[0].lower())
        if first in _PREFIXES:
            rest = ' '.join(parts[1:])
            _add(rest)
            _add(strip_accents(rest))

    # Variant: country-qualified (for disambiguation on Wikipedia)
    if country:
        _add(f"{no_accent} {normalize_display(country)}")

    # Variant: generic "football club" suffix (sometimes needed to find the right page)
    _add(f"{no_accent} football club")

    return candidates


def slugify(name):
    """Return a filesystem-safe ASCII slug for *name* (max 80 chars)."""
    name = strip_accents(name.lower())
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[\s_-]+', '_', name.strip())
    return name[:80]
