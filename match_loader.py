"""
match_loader.py
Lee un Excel (.xlsx) con enfrentamientos y devuelve una lista de dicts.
Columnas esperadas (flexible en mayúsculas/espacios):
  EQUIPO A | PAIS EQUIPO A | EQUIPO B | PAIS EQUIPO B
"""

import re
from pathlib import Path


def _normalize_col(col: str) -> str:
    """Normaliza nombre de columna para comparación flexible."""
    return re.sub(r"\s+", " ", str(col).strip().upper())


# Mapeo flexible: clave normalizada → nombre canónico
_COL_MAP = {
    "EQUIPO A": "equipo_a",
    "EQUIPO_A": "equipo_a",
    "EQUPOA": "equipo_a",
    "TEAM A": "equipo_a",
    "PAIS EQUIPO A": "pais_a",
    "PAIS_EQUIPO_A": "pais_a",
    "PAÍS EQUIPO A": "pais_a",
    "COUNTRY A": "pais_a",
    "EQUIPO B": "equipo_b",
    "EQUIPO_B": "equipo_b",
    "EQUPOB": "equipo_b",   # typo from original CSV: EQUPO B
    "EQUPO B": "equipo_b",
    "TEAM B": "equipo_b",
    "PAIS EQUIPO B": "pais_b",
    "PAIS_EQUIPO_B": "pais_b",
    "PAÍS EQUIPO B": "pais_b",
    "COUNTRY B": "pais_b",
}


def load_matches(path: str | Path) -> list[dict]:
    """
    Lee un Excel y retorna lista de dicts con keys:
      equipo_a, pais_a, equipo_b, pais_b
    Lanza ValueError si faltan columnas obligatorias.
    """
    try:
        import openpyxl
    except ImportError as exc:
        raise ImportError("openpyxl es requerido: pip install openpyxl") from exc

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("El archivo Excel está vacío.")

    # Primera fila = encabezados
    raw_headers = [str(h) if h is not None else "" for h in rows[0]]
    col_index: dict[str, int] = {}

    for i, raw in enumerate(raw_headers):
        norm = _normalize_col(raw)
        canonical = _COL_MAP.get(norm)
        if canonical and canonical not in col_index:
            col_index[canonical] = i

    # Verificar columnas requeridas
    required = {"equipo_a", "equipo_b"}
    missing = required - set(col_index.keys())
    if missing:
        raise ValueError(
            f"No se encontraron las columnas requeridas: {missing}. "
            f"Encabezados detectados: {raw_headers}"
        )

    matches: list[dict] = []
    for row in rows[1:]:
        # Saltar filas completamente vacías
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        def get(key: str) -> str:
            idx = col_index.get(key)
            if idx is None or idx >= len(row):
                return ""
            val = row[idx]
            return str(val).strip() if val is not None else ""

        equipo_a = get("equipo_a")
        equipo_b = get("equipo_b")
        if not equipo_a or not equipo_b:
            continue

        matches.append(
            {
                "equipo_a": equipo_a,
                "pais_a": get("pais_a"),
                "equipo_b": equipo_b,
                "pais_b": get("pais_b"),
                # campos de estado que se llenarán después
                "logo_a_path": None,
                "logo_a_status": "PENDING",
                "logo_a_source": None,
                "logo_b_path": None,
                "logo_b_status": "PENDING",
                "logo_b_source": None,
                "background_path": None,
                "match_status": "PENDING",
                "output_1920": None,
                "output_3840": None,
                "output_480": None,
                "error": None,
            }
        )

    return matches
