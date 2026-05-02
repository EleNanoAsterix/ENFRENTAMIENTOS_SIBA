"""
reporter.py
Genera reporte Excel (+ CSV opcional) con hojas:
  GENERADAS | FALLIDAS | LOGOS
"""

import csv
from datetime import datetime
from pathlib import Path


def generate_report(
    matches: list[dict],
    logo_results: dict,     # {team_key: LogoResult}
    output_dir: Path | str,
    run_ts: str | None = None,
) -> dict:
    """
    Genera report.xlsx y report.csv en output_dir.

    Parámetros:
        matches:      lista de dicts de enfrentamientos (con campos de status)
        logo_results: mapa team_key → LogoResult (team_key = "equipo|pais")
        output_dir:   carpeta de salida del run
        run_ts:       timestamp del run (default: ahora)

    Retorna:
        {"xlsx": path_xlsx, "csv": path_csv}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_ts = run_ts or datetime.now().strftime("%Y%m%d-%H%M%S")

    xlsx_path = output_dir / "report.xlsx"
    csv_path = output_dir / "report.csv"

    _write_xlsx(matches, logo_results, xlsx_path, run_ts)
    _write_csv(matches, logo_results, csv_path)

    return {"xlsx": str(xlsx_path), "csv": str(csv_path)}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _matchup_label(m: dict) -> str:
    return f"{m['equipo_a']} vs {m['equipo_b']}"


def _write_xlsx(
    matches: list[dict],
    logo_results: dict,
    path: Path,
    run_ts: str,
) -> None:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise ImportError("openpyxl es requerido: pip install openpyxl")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # quitar hoja por defecto

    # ── Hoja GENERADAS ────────────────────────────────────────────────
    ws_gen = wb.create_sheet("GENERADAS")
    gen_headers = [
        "Enfrentamiento", "Equipo A", "País A", "Equipo B", "País B",
        "Output 1920x1080", "Output 3840x2160", "Output 480x720",
        "Fecha/Hora",
    ]
    ws_gen.append(gen_headers)
    _style_header(ws_gen, gen_headers)

    gen_rows = [m for m in matches if m.get("match_status") == "GENERATED"]
    for m in gen_rows:
        ws_gen.append([
            _matchup_label(m),
            m["equipo_a"],
            m.get("pais_a", ""),
            m["equipo_b"],
            m.get("pais_b", ""),
            m.get("output_1920") or "",
            m.get("output_3840") or "",
            m.get("output_480") or "",
            run_ts,
        ])

    # ── Hoja FALLIDAS ─────────────────────────────────────────────────
    ws_fail = wb.create_sheet("FALLIDAS")
    fail_headers = [
        "Enfrentamiento", "Equipo A", "Equipo B",
        "Estado Logo A", "Estado Logo B", "Estado Fondo",
        "Motivo", "Detalle Error",
    ]
    ws_fail.append(fail_headers)
    _style_header(ws_fail, fail_headers, fill="C00000")

    fail_rows = [m for m in matches if m.get("match_status") != "GENERATED"]
    for m in fail_rows:
        reasons = []
        logo_a_st = m.get("logo_a_status", "")
        logo_b_st = m.get("logo_b_status", "")
        bg_st = "OK" if m.get("background_path") else "MISSING"

        if not m.get("logo_a_path") or "NOT_FOUND" in logo_a_st:
            reasons.append("Logo A no encontrado")
        if not m.get("logo_b_path") or "NOT_FOUND" in logo_b_st:
            reasons.append("Logo B no encontrado")
        if bg_st == "MISSING":
            reasons.append("Fondo faltante")
        if m.get("match_status") == "FAILED":
            reasons.append("Error en generación")

        motivo = "; ".join(reasons) if reasons else m.get("match_status", "")
        ws_fail.append([
            _matchup_label(m),
            m["equipo_a"],
            m["equipo_b"],
            logo_a_st,
            logo_b_st,
            bg_st,
            motivo,
            m.get("error") or "",
        ])

    # ── Hoja LOGOS ────────────────────────────────────────────────────
    ws_logos = wb.create_sheet("LOGOS")
    logo_headers = [
        "Equipo", "País", "Fuente", "Formato", "Ruta Local",
        "URL Origen", "Tamaño Validado", "Estado",
    ]
    ws_logos.append(logo_headers)
    _style_header(ws_logos, logo_headers, fill="1F4E79")

    for team_key, lr in logo_results.items():
        parts = team_key.split("|", 1)
        team = parts[0]
        country = parts[1] if len(parts) > 1 else ""
        size_str = (
            f"{lr.validated_size[0]}x{lr.validated_size[1]}"
            if lr.validated_size and lr.validated_size != (0, 0)
            else ""
        )
        ws_logos.append([
            team,
            country,
            lr.source,
            lr.ext.lstrip(".") if lr.ext else "",
            str(lr.path) if lr.path else "",
            lr.origin_url or "",
            size_str,
            lr.status,
        ])

    # Auto-ajustar anchos de columna
    for ws in [ws_gen, ws_fail, ws_logos]:
        for col in ws.columns:
            max_len = max(
                (len(str(cell.value or "")) for cell in col), default=0
            )
            ws.column_dimensions[col[0].column_letter].width = min(
                max(max_len + 2, 12), 60
            )

    wb.save(path)


def _style_header(ws, headers: list, fill: str = "2E4057") -> None:
    """Aplica estilo a la fila de encabezados."""
    try:
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal="center", wrap_text=True)


def _write_csv(matches: list[dict], logo_results: dict, path: Path) -> None:
    """Escribe un CSV plano con el resumen de todos los enfrentamientos."""
    fieldnames = [
        "enfrentamiento", "equipo_a", "pais_a", "equipo_b", "pais_b",
        "logo_a_status", "logo_a_source", "logo_a_path",
        "logo_b_status", "logo_b_source", "logo_b_path",
        "background_path", "match_status",
        "output_1920", "output_3840", "output_480",
        "error",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for m in matches:
            row = {k: (m.get(k) or "") for k in fieldnames}
            row["enfrentamiento"] = _matchup_label(m)
            writer.writerow(row)
