"""
app.py
Aplicación Tkinter para generar imágenes de enfrentamientos deportivos.

Flujo:
  1. Cargar Excel con enfrentamientos.
  2. Configurar modo de fondo (global / por fila).
  3. Buscar/descargar logos automáticamente.
  4. Resolver logos faltantes manualmente.
  5. Generar imágenes.
  6. Ver reporte.
"""

import io
import os
import queue
import re
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ── Módulos del proyecto ───────────────────────────────────────────────────────
from match_loader import load_matches
from logo_fetcher import fetch_logo, set_manual_logo, LogoResult
from generator import generate_matchup
from reporter import generate_report

# ── Constantes de UI ───────────────────────────────────────────────────────────
APP_TITLE = "Generador de Enfrentamientos SIBA"
BG_COLOR = "#1a1a2e"
PANEL_COLOR = "#16213e"
ACCENT_COLOR = "#0f3460"
BTN_COLOR = "#e94560"
TEXT_COLOR = "#eaeaea"
OK_COLOR = "#4CAF50"
WARN_COLOR = "#FF9800"
ERR_COLOR = "#F44336"

COL_WIDTHS = {
    "#": 40,
    "Equipo A": 150,
    "País A": 90,
    "Equipo B": 150,
    "País B": 90,
    "Logo A": 120,
    "Logo B": 120,
    "Fondo": 90,
    "Estado": 100,
}

STATUS_COLORS = {
    "PENDING": WARN_COLOR,
    "OK_SVG": OK_COLOR,
    "OK_PNG": OK_COLOR,
    "OK_WIKI_SVG": OK_COLOR,
    "OK_WIKI_PNG": OK_COLOR,
    "OK_SPORTSDB_PNG": OK_COLOR,
    "MANUAL_OK": OK_COLOR,
    "CACHED": OK_COLOR,
    "NOT_FOUND": ERR_COLOR,
    "GENERATED": OK_COLOR,
    "FAILED": ERR_COLOR,
    "MISSING_LOGO_A": ERR_COLOR,
    "MISSING_LOGO_B": ERR_COLOR,
    "MISSING_BACKGROUND": WARN_COLOR,
    "READY": OK_COLOR,
}


def _status_color(status: str) -> str:
    if not status:
        return WARN_COLOR
    for k, v in STATUS_COLORS.items():
        if k in status.upper():
            return v
    if "OK" in status.upper() or "MANUAL" in status.upper():
        return OK_COLOR
    if "LOW" in status.upper():
        return WARN_COLOR
    return ERR_COLOR


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x750")
        self.minsize(900, 600)
        self.configure(bg=BG_COLOR)
        self.resizable(True, True)

        # ── Estado ────────────────────────────────────────────────────
        self.matches: list[dict] = []
        self.logo_results: dict[str, LogoResult] = {}
        self.global_bg_path: str = ""
        self.bg_mode = tk.StringVar(value="global")  # "global" | "per_row"
        self.outline_var = tk.BooleanVar(value=False)
        self.outline_width_var = tk.IntVar(value=8)
        self.enhance_var = tk.BooleanVar(value=False)
        self.run_ts: str = ""

        # Cola de mensajes del hilo de descarga/generación
        self._msg_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._poll_queue()

    # ── Construcción de UI ─────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Título ─────────────────────────────────────────────────────
        title_bar = tk.Frame(self, bg=ACCENT_COLOR, pady=8)
        title_bar.pack(fill="x")
        tk.Label(
            title_bar,
            text=APP_TITLE,
            bg=ACCENT_COLOR,
            fg=TEXT_COLOR,
            font=("Helvetica", 16, "bold"),
        ).pack(side="left", padx=16)

        # ── Panel izquierdo (controles) ────────────────────────────────
        left = tk.Frame(self, bg=PANEL_COLOR, width=260, padx=10, pady=10)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        self._build_left_panel(left)

        # ── Panel derecho (tabla + log) ────────────────────────────────
        right = tk.Frame(self, bg=BG_COLOR)
        right.pack(side="left", fill="both", expand=True)

        self._build_table(right)
        self._build_log(right)

    def _lbl(self, parent, text, **kw) -> tk.Label:
        kw.setdefault("bg", PANEL_COLOR)
        kw.setdefault("fg", TEXT_COLOR)
        kw.setdefault("anchor", "w")
        return tk.Label(parent, text=text, **kw)

    def _btn(self, parent, text, cmd, **kw) -> tk.Button:
        kw.setdefault("bg", BTN_COLOR)
        kw.setdefault("fg", "white")
        kw.setdefault("activebackground", "#c73652")
        kw.setdefault("relief", "flat")
        kw.setdefault("cursor", "hand2")
        kw.setdefault("padx", 6)
        kw.setdefault("pady", 4)
        return tk.Button(parent, text=text, command=cmd, **kw)

    def _build_left_panel(self, parent):
        # ── Cargar Excel ───────────────────────────────────────────────
        self._lbl(parent, "📋 Enfrentamientos", font=("Helvetica", 11, "bold")).pack(
            fill="x", pady=(0, 4)
        )
        self._btn(parent, "📂 Cargar Excel (.xlsx)", self._load_excel).pack(
            fill="x", pady=2
        )
        self.lbl_file = self._lbl(parent, "Sin archivo cargado", fg="#aaaaaa")
        self.lbl_file.pack(fill="x", pady=(0, 10))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=6)

        # ── Modo de fondo ──────────────────────────────────────────────
        self._lbl(parent, "🖼 Modo de fondo", font=("Helvetica", 11, "bold")).pack(
            fill="x", pady=(0, 4)
        )
        tk.Radiobutton(
            parent,
            text="Mismo fondo para todos",
            variable=self.bg_mode,
            value="global",
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            selectcolor=ACCENT_COLOR,
            activebackground=PANEL_COLOR,
            command=self._on_bg_mode_change,
        ).pack(anchor="w")
        tk.Radiobutton(
            parent,
            text="Fondo por enfrentamiento",
            variable=self.bg_mode,
            value="per_row",
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            selectcolor=ACCENT_COLOR,
            activebackground=PANEL_COLOR,
            command=self._on_bg_mode_change,
        ).pack(anchor="w")

        self.btn_global_bg = self._btn(
            parent, "📁 Elegir fondo global", self._choose_global_bg
        )
        self.btn_global_bg.pack(fill="x", pady=4)
        self.lbl_global_bg = self._lbl(parent, "Sin fondo seleccionado", fg="#aaaaaa")
        self.lbl_global_bg.pack(fill="x", pady=(0, 10))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=6)

        # ── Opciones avanzadas ─────────────────────────────────────────
        self._lbl(parent, "⚙ Opciones avanzadas", font=("Helvetica", 11, "bold")).pack(
            fill="x", pady=(0, 4)
        )
        tk.Checkbutton(
            parent,
            text="Contorno blanco en logos",
            variable=self.outline_var,
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            selectcolor=ACCENT_COLOR,
            activebackground=PANEL_COLOR,
            command=self._on_outline_toggle,
        ).pack(anchor="w")

        outline_frame = tk.Frame(parent, bg=PANEL_COLOR)
        outline_frame.pack(fill="x", pady=2)
        self._lbl(outline_frame, "  Grosor:", width=8).pack(side="left")
        self.spin_outline = tk.Spinbox(
            outline_frame,
            from_=1, to=30,
            textvariable=self.outline_width_var,
            width=4,
            bg=ACCENT_COLOR,
            fg=TEXT_COLOR,
            buttonbackground=ACCENT_COLOR,
        )
        self.spin_outline.pack(side="left")
        self._lbl(outline_frame, "px").pack(side="left")

        tk.Checkbutton(
            parent,
            text="Auto-mejorar fondo",
            variable=self.enhance_var,
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            selectcolor=ACCENT_COLOR,
            activebackground=PANEL_COLOR,
        ).pack(anchor="w", pady=(4, 0))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)

        # ── Acciones principales ───────────────────────────────────────
        self._lbl(
            parent, "🚀 Acciones", font=("Helvetica", 11, "bold")
        ).pack(fill="x", pady=(0, 4))

        self._btn(
            parent, "🔍 Buscar/Descargar logos", self._download_logos
        ).pack(fill="x", pady=2)
        self._btn(
            parent, "✏️ Resolver logos manualmente", self._manual_resolve
        ).pack(fill="x", pady=2)
        self._btn(
            parent, "▶ Generar imágenes", self._generate_all, bg="#1a8c3e"
        ).pack(fill="x", pady=6)
        self._btn(
            parent, "📊 Ver / Abrir reporte", self._open_report, bg=ACCENT_COLOR
        ).pack(fill="x", pady=2)

        # Barra de progreso
        self._lbl(parent, "Progreso:").pack(fill="x", pady=(10, 0))
        self.progress_var = tk.DoubleVar()
        self.progressbar = ttk.Progressbar(
            parent, variable=self.progress_var, maximum=100
        )
        self.progressbar.pack(fill="x", pady=2)
        self.lbl_progress = self._lbl(parent, "")
        self.lbl_progress.pack(fill="x")

    def _build_table(self, parent):
        frame = tk.Frame(parent, bg=BG_COLOR)
        frame.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        columns = list(COL_WIDTHS.keys())
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=16)

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Treeview",
            background="#1a1a2e",
            foreground=TEXT_COLOR,
            rowheight=26,
            fieldbackground="#1a1a2e",
        )
        style.configure("Treeview.Heading", background=ACCENT_COLOR, foreground="white")
        style.map("Treeview", background=[("selected", ACCENT_COLOR)])

        for col, w in COL_WIDTHS.items():
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, minwidth=30, anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # Botón rápido para asignar fondo por fila
        btn_row_bg = self._btn(
            frame, "🖼 Asignar fondo a fila seleccionada", self._set_row_bg, bg=ACCENT_COLOR
        )
        btn_row_bg.grid(row=2, column=0, sticky="w", pady=2)

    def _build_log(self, parent):
        frame = tk.Frame(parent, bg=BG_COLOR)
        frame.pack(fill="x", padx=8, pady=(0, 8))
        self._lbl(frame, "📝 Log", bg=BG_COLOR, font=("Helvetica", 9)).pack(
            anchor="w"
        )
        self.log_text = tk.Text(
            frame, height=6, bg="#0d0d1a", fg="#aaaaaa",
            font=("Courier", 9), state="disabled", wrap="word",
        )
        self.log_text.pack(fill="x")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=sb.set)

    # ── Acciones ───────────────────────────────────────────────────────────────

    def _load_excel(self):
        path = filedialog.askopenfilename(
            title="Cargar Excel de enfrentamientos",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            self.matches = load_matches(path)
        except Exception as e:
            messagebox.showerror("Error al cargar", str(e))
            return

        fname = Path(path).name
        self.lbl_file.config(text=f"{fname} ({len(self.matches)} filas)")
        self._log(f"Cargado: {fname} — {len(self.matches)} enfrentamientos.")
        self._refresh_table()

    def _on_bg_mode_change(self):
        mode = self.bg_mode.get()
        state = "normal" if mode == "global" else "disabled"
        self.btn_global_bg.config(state=state)

    def _choose_global_bg(self):
        path = filedialog.askopenfilename(
            title="Elegir imagen de fondo global",
            filetypes=[
                ("Imágenes", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                ("Todos", "*.*"),
            ],
        )
        if not path:
            return
        self.global_bg_path = path
        fname = Path(path).name
        self.lbl_global_bg.config(text=fname, fg=OK_COLOR)
        if self.bg_mode.get() == "global":
            for m in self.matches:
                m["background_path"] = path
            self._refresh_table()
        self._log(f"Fondo global: {fname}")

    def _set_row_bg(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selección", "Selecciona un enfrentamiento en la tabla.")
            return
        path = filedialog.askopenfilename(
            title="Elegir fondo para el enfrentamiento seleccionado",
            filetypes=[
                ("Imágenes", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                ("Todos", "*.*"),
            ],
        )
        if not path:
            return
        for item_id in sel:
            row_idx = self._item_to_row_idx(item_id)
            if row_idx is not None:
                self.matches[row_idx]["background_path"] = path
        self._refresh_table()
        self._log(f"Fondo asignado a {len(sel)} fila(s): {Path(path).name}")

    def _on_outline_toggle(self):
        pass

    # ── Descarga de logos ──────────────────────────────────────────────────────

    def _download_logos(self):
        if not self.matches:
            messagebox.showinfo("Sin datos", "Primero carga un Excel de enfrentamientos.")
            return
        self._log("Iniciando descarga de logos…")
        self.progress_var.set(0)
        t = threading.Thread(target=self._download_logos_worker, daemon=True)
        t.start()

    def _download_logos_worker(self):
        teams_seen: dict[str, tuple[str, str]] = {}  # key → (team, country)
        for m in self.matches:
            for side in ("a", "b"):
                team = m[f"equipo_{side}"]
                country = m.get(f"pais_{side}", "")
                key = f"{team}|{country}"
                teams_seen[key] = (team, country)

        total = len(teams_seen)
        done = 0

        for key, (team, country) in teams_seen.items():
            self._q(f"[{done+1}/{total}] Buscando logo: {team} ({country})")
            try:
                lr = fetch_logo(
                    team, country,
                    progress_callback=lambda msg: self._q(f"  {msg}"),
                )
            except Exception as e:
                from logo_fetcher import LogoResult
                lr = LogoResult()
                lr.status = f"ERROR:{e}"
                lr.error = str(e)
            self.logo_results[key] = lr
            done += 1
            pct = done / total * 100
            self._q(f"__PROGRESS__{pct:.1f}")

        # Asignar logos a los matches
        for m in self.matches:
            for side in ("a", "b"):
                team = m[f"equipo_{side}"]
                country = m.get(f"pais_{side}", "")
                key = f"{team}|{country}"
                lr = self.logo_results.get(key)
                if lr and lr.path:
                    m[f"logo_{side}_path"] = str(lr.path)
                    m[f"logo_{side}_status"] = lr.status
                    m[f"logo_{side}_source"] = lr.source
                else:
                    m[f"logo_{side}_status"] = "NOT_FOUND" if not lr else lr.status

        self._q("__REFRESH__")
        self._q("Descarga de logos completada.")

    # ── Resolución manual ──────────────────────────────────────────────────────

    def _manual_resolve(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(
                "Selección", "Selecciona un enfrentamiento para resolver logos."
            )
            return
        item_id = sel[0]
        row_idx = self._item_to_row_idx(item_id)
        if row_idx is None:
            return
        m = self.matches[row_idx]
        ManualLogoDialog(self, m, self.logo_results, on_save=self._on_manual_saved)

    def _on_manual_saved(self, match: dict, logo_results: dict):
        self.logo_results.update(logo_results)
        for m in self.matches:
            if (
                m["equipo_a"] == match["equipo_a"]
                and m["equipo_b"] == match["equipo_b"]
            ):
                m.update({k: match[k] for k in match if k in m})
        self._refresh_table()

    # ── Generación ─────────────────────────────────────────────────────────────

    def _generate_all(self):
        if not self.matches:
            messagebox.showinfo("Sin datos", "Primero carga un Excel de enfrentamientos.")
            return
        ready = [
            m for m in self.matches
            if m.get("logo_a_path") and m.get("logo_b_path") and m.get("background_path")
        ]
        if not ready:
            messagebox.showwarning(
                "Sin enfrentamientos listos",
                "Ningún enfrentamiento tiene logos y fondo completos.\n"
                "Descarga logos y asigna un fondo primero.",
            )
            return

        self.run_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._log(f"Iniciando generación: {len(ready)} enfrentamientos (run {self.run_ts})…")
        self.progress_var.set(0)

        t = threading.Thread(target=self._generate_worker, args=(self.run_ts,), daemon=True)
        t.start()

    def _generate_worker(self, run_ts: str):
        output_dir = Path("output") / run_ts

        ready = [
            m for m in self.matches
            if m.get("logo_a_path") and m.get("logo_b_path") and m.get("background_path")
        ]
        not_ready = [m for m in self.matches if m not in ready]
        for m in not_ready:
            reasons = []
            if not m.get("logo_a_path"):
                reasons.append("MISSING_LOGO_A")
            if not m.get("logo_b_path"):
                reasons.append("MISSING_LOGO_B")
            if not m.get("background_path"):
                reasons.append("MISSING_BACKGROUND")
            m["match_status"] = "+".join(reasons) if reasons else "PENDING"

        total = len(ready)
        for i, m in enumerate(ready):
            label = f"{m['equipo_a']} vs {m['equipo_b']}"
            self._q(f"[{i+1}/{total}] Generando: {label}")
            try:
                res = generate_matchup(
                    match=m,
                    output_dir=output_dir,
                    outline=self.outline_var.get(),
                    outline_width=self.outline_width_var.get(),
                    auto_enhance=self.enhance_var.get(),
                )
                if res["success"]:
                    m["match_status"] = "GENERATED"
                    m["output_1920"] = res.get("output_1920")
                    m["output_3840"] = res.get("output_3840")
                    m["output_480"] = res.get("output_480")
                    m["error"] = res.get("error") or ""
                    self._q(f"  ✓ {label}")
                else:
                    m["match_status"] = "FAILED"
                    m["error"] = res.get("error", "Error desconocido")
                    self._q(f"  ✗ {label}: {m['error']}")
            except Exception as e:
                m["match_status"] = "FAILED"
                m["error"] = str(e)
                self._q(f"  ✗ {label}: {e}")

            pct = (i + 1) / total * 100
            self._q(f"__PROGRESS__{pct:.1f}")

        # Generar reporte
        self._q("Generando reporte…")
        try:
            rep = generate_report(
                matches=self.matches,
                logo_results=self.logo_results,
                output_dir=output_dir,
                run_ts=run_ts,
            )
            self._q(f"Reporte guardado: {rep['xlsx']}")
            self._last_report = rep
        except Exception as e:
            self._q(f"Error generando reporte: {e}")

        self._q("__REFRESH__")
        generated = sum(1 for m in self.matches if m.get("match_status") == "GENERATED")
        failed = sum(1 for m in self.matches if m.get("match_status") == "FAILED")
        self._q(f"✅ Listo: {generated} generadas, {failed} fallidas. Carpeta: output/{run_ts}/")

    # ── Reporte ────────────────────────────────────────────────────────────────

    def _open_report(self):
        if hasattr(self, "_last_report"):
            path = self._last_report.get("xlsx") or self._last_report.get("csv")
            if path and Path(path).exists():
                import subprocess, sys
                if sys.platform == "win32":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
                return
        # Buscar última carpeta de output
        output_root = Path("output")
        if output_root.exists():
            runs = sorted(output_root.iterdir(), reverse=True)
            for run_dir in runs:
                rep = run_dir / "report.xlsx"
                if rep.exists():
                    import subprocess, sys
                    if sys.platform == "win32":
                        os.startfile(str(rep))
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", str(rep)])
                    else:
                        subprocess.Popen(["xdg-open", str(rep)])
                    return
        messagebox.showinfo("Reporte", "No se encontró ningún reporte. Genera imágenes primero.")

    # ── Tabla ──────────────────────────────────────────────────────────────────

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for i, m in enumerate(self.matches):
            logo_a_st = m.get("logo_a_status") or "PENDING"
            logo_b_st = m.get("logo_b_status") or "PENDING"
            bg_st = "✓" if m.get("background_path") else "—"
            match_st = m.get("match_status") or "PENDING"

            tag_a = _status_color(logo_a_st)
            tag_b = _status_color(logo_b_st)
            tag_m = _status_color(match_st)

            item_id = self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    i + 1,
                    m["equipo_a"],
                    m.get("pais_a", ""),
                    m["equipo_b"],
                    m.get("pais_b", ""),
                    logo_a_st,
                    logo_b_st,
                    bg_st,
                    match_st,
                ),
            )
            # Colorear filas alternadas
            self.tree.tag_configure(f"row_{i}", background="#1a1a2e" if i % 2 == 0 else "#151527")

    def _item_to_row_idx(self, item_id: str) -> int | None:
        try:
            return int(item_id)
        except (ValueError, TypeError):
            return None

    # ── Log ────────────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _q(self, msg: str):
        """Envía mensaje a la cola (seguro desde hilos)."""
        self._msg_queue.put(msg)

    def _poll_queue(self):
        """Procesa mensajes de la cola en el hilo principal."""
        while not self._msg_queue.empty():
            msg = self._msg_queue.get_nowait()
            if msg.startswith("__PROGRESS__"):
                try:
                    pct = float(msg.replace("__PROGRESS__", ""))
                    self.progress_var.set(pct)
                    self.lbl_progress.config(text=f"{pct:.0f}%")
                except ValueError:
                    pass
            elif msg == "__REFRESH__":
                self._refresh_table()
                self.progress_var.set(100)
                self.lbl_progress.config(text="100%")
            else:
                self._log(msg)
        self.after(100, self._poll_queue)


# ── Diálogo de resolución manual ──────────────────────────────────────────────

class ManualLogoDialog(tk.Toplevel):
    """Ventana para seleccionar logos manualmente para un enfrentamiento."""

    def __init__(self, parent, match: dict, logo_results: dict, on_save=None):
        super().__init__(parent)
        self.title(f"Resolver logos: {match['equipo_a']} vs {match['equipo_b']}")
        self.configure(bg=BG_COLOR)
        self.resizable(False, False)
        self.grab_set()

        self.match = match
        self.logo_results = dict(logo_results)
        self.on_save = on_save

        self._new_logo_a: str = match.get("logo_a_path") or ""
        self._new_logo_b: str = match.get("logo_b_path") or ""

        self._build()

    def _build(self):
        pad = {"padx": 12, "pady": 6}

        def section(text):
            tk.Label(
                self, text=text, bg=ACCENT_COLOR, fg="white",
                font=("Helvetica", 11, "bold"), anchor="w",
            ).pack(fill="x", **pad)

        def logo_row(side: str, label: str, current_path: str):
            frame = tk.Frame(self, bg=BG_COLOR)
            frame.pack(fill="x", **pad)
            tk.Label(
                frame, text=label, bg=BG_COLOR, fg=TEXT_COLOR, width=22, anchor="w"
            ).pack(side="left")
            path_var = tk.StringVar(value=current_path or "No seleccionado")
            lbl = tk.Label(
                frame, textvariable=path_var, bg=BG_COLOR, fg="#aaaaaa",
                width=28, anchor="w", wraplength=180,
            )
            lbl.pack(side="left", padx=4)

            def choose(pv=path_var, s=side):
                p = filedialog.askopenfilename(
                    title=f"Elegir logo para {label}",
                    filetypes=[
                        ("Imágenes", "*.svg *.png *.jpg *.jpeg *.webp"),
                        ("Todos", "*.*"),
                    ],
                )
                if p:
                    pv.set(Path(p).name)
                    if s == "a":
                        self._new_logo_a = p
                    else:
                        self._new_logo_b = p

            tk.Button(
                frame, text="📂 Elegir",
                command=choose,
                bg=BTN_COLOR, fg="white", relief="flat", cursor="hand2",
            ).pack(side="left", padx=4)

        section(f"🅰  {self.match['equipo_a']}")
        logo_row("a", "Logo Equipo A:", self._new_logo_a)

        section(f"🅱  {self.match['equipo_b']}")
        logo_row("b", "Logo Equipo B:", self._new_logo_b)

        # Botones
        btn_frame = tk.Frame(self, bg=BG_COLOR)
        btn_frame.pack(fill="x", pady=10, padx=12)
        tk.Button(
            btn_frame, text="✅ Guardar",
            command=self._save,
            bg=OK_COLOR, fg="white", relief="flat", cursor="hand2", padx=10,
        ).pack(side="right", padx=4)
        tk.Button(
            btn_frame, text="Cancelar",
            command=self.destroy,
            bg=ACCENT_COLOR, fg="white", relief="flat", cursor="hand2", padx=10,
        ).pack(side="right", padx=4)

    def _save(self):
        for side, path in [("a", self._new_logo_a), ("b", self._new_logo_b)]:
            if path and Path(path).exists():
                team = self.match[f"equipo_{side}"]
                country = self.match.get(f"pais_{side}", "")
                key = f"{team}|{country}"
                try:
                    lr = set_manual_logo(team, country, path)
                    self.logo_results[key] = lr
                    self.match[f"logo_{side}_path"] = str(lr.path)
                    self.match[f"logo_{side}_status"] = lr.status
                    self.match[f"logo_{side}_source"] = "manual"
                except Exception as e:
                    messagebox.showerror("Error", f"Error al guardar logo: {e}")
                    return

        if self.on_save:
            self.on_save(self.match, self.logo_results)
        self.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
