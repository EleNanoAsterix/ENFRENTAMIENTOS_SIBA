"""
match_loader.py – Load match data from an Excel (.xlsx) file.

Expected columns (case-insensitive, trimmed):
    EQUIPO A | PAIS EQUIPO A | EQUIPO B | PAIS EQUIPO B

Returns a list of match-dicts that are used throughout the application.
"""

import pandas as pd

# Canonical column names expected in the Excel file.
REQUIRED_COLUMNS = ('EQUIPO A', 'PAIS EQUIPO A', 'EQUIPO B', 'PAIS EQUIPO B')


def load_matches(excel_path):
    """Read *excel_path* and return a list of match-dicts.

    Each dict has the following keys (all others are filled in later):
        id, equipo_a, pais_a, equipo_b, pais_b,
        logo_a, logo_b, logo_a_status, logo_b_status,
        logo_a_source, logo_b_source, logo_a_url, logo_b_url,
        logo_a_size, logo_b_size, background,
        match_status, output_1920, output_3840, output_480, error

    Raises:
        ValueError if required columns are missing or no valid rows found.
    """
    df = pd.read_excel(excel_path, dtype=str)

    # Normalise column headers: strip whitespace and upper-case
    df.columns = [str(c).strip().upper() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Columnas faltantes en el Excel: {', '.join(missing)}\n"
            f"Se esperan exactamente: {', '.join(REQUIRED_COLUMNS)}"
        )

    matches = []
    for i, row in df.iterrows():
        equipo_a = str(row.get('EQUIPO A', '')).strip()
        equipo_b = str(row.get('EQUIPO B', '')).strip()

        # Skip blank or NaN rows
        if not equipo_a or equipo_a.lower() == 'nan':
            continue
        if not equipo_b or equipo_b.lower() == 'nan':
            continue

        match = {
            'id': len(matches) + 1,
            # From Excel
            'equipo_a': equipo_a,
            'pais_a': str(row.get('PAIS EQUIPO A', '')).strip(),
            'equipo_b': equipo_b,
            'pais_b': str(row.get('PAIS EQUIPO B', '')).strip(),
            # Logo info (populated by logo_fetcher)
            'logo_a': None,
            'logo_b': None,
            'logo_a_status': 'PENDING',
            'logo_b_status': 'PENDING',
            'logo_a_source': None,
            'logo_b_source': None,
            'logo_a_url': None,
            'logo_b_url': None,
            'logo_a_size': None,
            'logo_b_size': None,
            # Background (set by user)
            'background': None,
            # Generation results
            'match_status': 'PENDING',
            'output_1920': None,
            'output_3840': None,
            'output_480': None,
            'error': None,
        }
        matches.append(match)

    if not matches:
        raise ValueError(
            "No se encontraron enfrentamientos válidos en el Excel. "
            "Verifique que las filas no estén vacías."
        )

    return matches
