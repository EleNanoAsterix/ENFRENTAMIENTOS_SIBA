"""
reporter.py – Generate an Excel report after a batch generation run.

The workbook contains three sheets:

  GENERADAS  – successfully generated matches + output file paths
  FALLIDAS   – matches that could not be generated + reason
  LOGOS      – one row per unique team, with logo source / status / URL
"""

import os

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ── Colour palette ─────────────────────────────────────────────────────────────
_HDR_FILL   = PatternFill(start_color='1F497D', end_color='1F497D', fill_type='solid')
_HDR_FONT   = Font(color='FFFFFF', bold=True)
_GREEN_FILL = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
_RED_FILL   = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
_YELLOW_FILL = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')


def generate_report(output_dir, matches):
    """Build ``report.xlsx`` inside *output_dir* and return its path.

    Args:
        output_dir: directory that already contains the generated images.
        matches:    list of match-dicts (as returned by match_loader and
                    populated by the logo_fetcher + generator).

    Returns:
        Absolute path to the created ``report.xlsx`` file.
    """
    wb = openpyxl.Workbook()

    # ── Sheet 1 : GENERADAS ────────────────────────────────────────────────
    ws_gen = wb.active
    ws_gen.title = 'GENERADAS'
    _write_header(ws_gen, [
        'Equipo A', 'País A', 'Equipo B', 'País B',
        'Imagen 1920×1080', 'Imagen 3840×2160', 'Imagen 480×720',
    ])

    # ── Sheet 2 : FALLIDAS ─────────────────────────────────────────────────
    ws_fail = wb.create_sheet('FALLIDAS')
    _write_header(ws_fail, [
        'Equipo A', 'País A', 'Equipo B', 'País B',
        'Motivo', 'Detalle',
    ])

    # ── Sheet 3 : LOGOS ────────────────────────────────────────────────────
    ws_logos = wb.create_sheet('LOGOS')
    _write_header(ws_logos, [
        'Equipo', 'País', 'Fuente', 'Formato', 'Estado',
        'Tamaño (px)', 'URL Origen', 'Ruta Local',
    ])

    logo_seen = {}   # (team_lower, country_lower) → row data

    for match in matches:
        a, pa = match['equipo_a'], match['pais_a']
        b, pb = match['equipo_b'], match['pais_b']

        if match.get('match_status') == 'GENERATED':
            row = [
                a, pa, b, pb,
                match.get('output_1920', ''),
                match.get('output_3840', ''),
                match.get('output_480', ''),
            ]
            _append_row(ws_gen, row, _GREEN_FILL)
        else:
            row = [a, pa, b, pb,
                   match.get('match_status', 'UNKNOWN'),
                   match.get('error', '')]
            _append_row(ws_fail, row, _RED_FILL)

        # Collect logo info (deduplicated by team+country key)
        for side, team, country in (('a', a, pa), ('b', b, pb)):
            key = (team.lower(), country.lower())
            if key not in logo_seen:
                status  = match.get(f'logo_{side}_status', '')
                url     = match.get(f'logo_{side}_url') or ''
                path    = match.get(f'logo_{side}') or ''
                size    = match.get(f'logo_{side}_size')
                source  = match.get(f'logo_{side}_source') or ''
                fmt     = ('SVG' if path.lower().endswith('.svg')
                           else 'PNG' if path else '')
                size_str = (f"{size[0]}×{size[1]}" if size else '')
                logo_seen[key] = [team, country, source, fmt, status,
                                  size_str, url, path]

    for lr in logo_seen.values():
        status = lr[4]
        fill = (_GREEN_FILL if (status.startswith('OK') or status == 'MANUAL_OK')
                else _YELLOW_FILL if 'LOW' in status
                else _RED_FILL)
        _append_row(ws_logos, lr, fill)

    # ── Auto-fit column widths ─────────────────────────────────────────────
    for ws in (ws_gen, ws_fail, ws_logos):
        _autofit(ws)

    report_path = os.path.join(output_dir, 'report.xlsx')
    wb.save(report_path)
    return report_path


# ── Internal helpers ───────────────────────────────────────────────────────────

def _write_header(ws, columns):
    ws.append(columns)
    for cell in ws[1]:
        cell.fill      = _HDR_FILL
        cell.font      = _HDR_FONT
        cell.alignment = Alignment(horizontal='center')


def _append_row(ws, values, fill):
    ws.append(values)
    row_idx = ws.max_row
    for cell in ws[row_idx]:
        cell.fill = fill


def _autofit(ws):
    for col in ws.columns:
        max_len  = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or '')))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 3, 70)
