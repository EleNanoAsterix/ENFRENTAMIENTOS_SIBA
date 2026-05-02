"""
app.py – SIBA Batch Matchup Generator

Main Tkinter application that orchestrates the full pipeline:
  1. Load Excel with match list
  2. Configure background (global or per-match)
  3. Auto-fetch logos (Wikipedia → TheSportsDB → manual fallback)
  4. Generate images in three resolutions
  5. Produce an Excel report
"""

import json
import os
import queue
import shutil
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from logo_fetcher import fetch_logo
from match_loader import load_matches
from generator import generate_single_enfrentamiento
from reporter import generate_report
from normalizer import slugify

# ── Directory layout ───────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(_BASE, 'cache', 'logos')
OUTPUT_DIR = os.path.join(_BASE, 'output')

# ── Status → short label for Treeview ─────────────────────────────────────────
STATUS_LABELS = {
    'OK_WIKI_SVG':          'Wiki SVG ✓',
    'OK_WIKI_PNG':          'Wiki PNG ✓',
    'OK_SPORTSDB_PNG':      'SportsDB ✓',
    'MANUAL_OK':            'Manual ✓',
    'LOW_QUALITY_WIKI':     'Wiki (baja cal.)',
    'LOW_QUALITY_SPORTSDB': 'SDB (baja cal.)',
    'NOT_FOUND':            'No encontrado',
    'PENDING':              'Pendiente',
    'ERROR':                'Error',
    'GENERATED':            'Generado ✓',
    'FAILED':               'Fallido ✗',
    'READY':                'Listo',
    'CACHED':               'Caché ✓',
}


def _status_to_label(s):
    return STATUS_LABELS.get(s, s or 'Pendiente')


def _row_tag(logo_a_st, logo_b_st, match_st, has_bg):
    """Return a Treeview tag name that reflects the row's overall status."""
    if match_st == 'GENERATED':
        return 'generated'
    if match_st == 'FAILED':
        return 'failed'

    def _ok(s):
        return s and (s.startswith('OK') or s == 'MANUAL_OK' or s == 'CACHED')

    if _ok(logo_a_st) and _ok(logo_b_st) and has_bg:
        return 'ready'
    if 'NOT_FOUND' in (logo_a_st, logo_b_st):
        return 'error'
    if 'ERROR' in (logo_a_st or '') or 'ERROR' in (logo_b_st or ''):
        return 'error'
    if 'LOW_QUALITY' in (logo_a_st or '') or 'LOW_QUALITY' in (logo_b_st or ''):
        return 'warning'
    return 'pending'


# ═══════════════════════════════════════════════════════════════════════════════

class BatchApp(tk.Tk):
    """Top-level Tkinter window for the SIBA batch generator."""

    def __init__(self):
        super().__init__()
        self.title('SIBA – Generador de Enfrentamientos por Lotes')
        self.geometry('1180x760')
        self.minsize(950, 620)

        # ── Application state ──────────────────────────────────────────────
        self.matches = []
        self.bg_mode = tk.StringVar(value='global')
        self.global_background = None

        # Options (mirroring app_generadora.py)
        self.add_outline    = tk.BooleanVar(value=False)
        self.outline_width  = tk.IntVar(value=3)
        self.auto_enhance   = tk.BooleanVar(value=False)

        # Threading
        self._queue  = queue.Queue()
        self._busy   = False

        self._setup_dirs()
        self._build_ui()
        self._poll()

    # ── Directory setup ────────────────────────────────────────────────────

    def _setup_dirs(self):
        for sub in ('wiki', 'sportsdb', 'manual'):
            os.makedirs(os.path.join(CACHE_DIR, sub), exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ══════════════════════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        top = tk.Frame(self)
        top.pack(fill='x', padx=10, pady=(8, 0))

        self._build_excel_section(top)
        self._build_bg_section(top)
        self._build_options_section(top)
        self._build_table_section()
        self._build_bottom_section()

    # ── 1. Excel ───────────────────────────────────────────────────────────

    def _build_excel_section(self, parent):
        frame = tk.LabelFrame(parent, text='1. Cargar Excel de Enfrentamientos',
                              padx=8, pady=6)
        frame.pack(fill='x', pady=3)

        row = tk.Frame(frame)
        row.pack(fill='x')

        tk.Button(row, text='Seleccionar Excel (.xlsx)',
                  command=self._load_excel,
                  bg='#1565c0', fg='white', padx=8).pack(side='left', padx=4)

        self._excel_label = tk.Label(row, text='Ningún archivo cargado',
                                     anchor='w', fg='gray')
        self._excel_label.pack(side='left', fill='x', expand=True)

    # ── 2. Background ──────────────────────────────────────────────────────

    def _build_bg_section(self, parent):
        frame = tk.LabelFrame(parent, text='2. Imagen de Fondo', padx=8, pady=6)
        frame.pack(fill='x', pady=3)

        row1 = tk.Frame(frame)
        row1.pack(fill='x')
        tk.Radiobutton(row1, text='Mismo fondo para todos',
                       variable=self.bg_mode, value='global',
                       command=self._on_bg_mode).pack(side='left')
        self._global_bg_btn = tk.Button(row1, text='Elegir fondo global…',
                                        command=self._pick_global_bg, padx=6)
        self._global_bg_btn.pack(side='left', padx=6)
        self._global_bg_label = tk.Label(row1, text='No seleccionado', fg='gray')
        self._global_bg_label.pack(side='left')

        tk.Radiobutton(frame,
                       text='Fondo por enfrentamiento  '
                            '(selecciona una fila y usa el botón de la tabla)',
                       variable=self.bg_mode, value='per_match',
                       command=self._on_bg_mode).pack(anchor='w')

    # ── 3. Options ─────────────────────────────────────────────────────────

    def _build_options_section(self, parent):
        frame = tk.LabelFrame(parent, text='3. Opciones', padx=8, pady=6)
        frame.pack(fill='x', pady=3)

        row = tk.Frame(frame)
        row.pack(fill='x')

        tk.Checkbutton(row, text='Contorno blanco en logos',
                       variable=self.add_outline).pack(side='left')
        tk.Label(row, text='   Grosor:').pack(side='left')
        tk.Scale(row, from_=1, to=8, orient='horizontal',
                 variable=self.outline_width, length=110).pack(side='left')

        tk.Checkbutton(frame,
                       text='Mejorar automáticamente imagen de fondo',
                       variable=self.auto_enhance).pack(anchor='w')

    # ── 4. Match table ─────────────────────────────────────────────────────

    def _build_table_section(self):
        frame = tk.LabelFrame(self, text='4. Enfrentamientos', padx=8, pady=6)
        frame.pack(fill='both', expand=True, padx=10, pady=3)

        # Action buttons above table
        btn_row = tk.Frame(frame)
        btn_row.pack(fill='x', pady=(0, 5))

        tk.Button(btn_row, text='🔍  Buscar / Descargar Logos',
                  command=self._fetch_logos,
                  bg='#2e7d32', fg='white', padx=8).pack(side='left', padx=2)

        tk.Button(btn_row, text='🖼  Resolver Logo Manual',
                  command=self._manual_logo, padx=8).pack(side='left', padx=2)

        self._per_match_btn = tk.Button(
            btn_row, text='🌄  Elegir Fondo (seleccionado)',
            command=self._pick_per_match_bg, padx=8, state='disabled')
        self._per_match_btn.pack(side='left', padx=2)

        self._count_label = tk.Label(btn_row, text='', fg='#444')
        self._count_label.pack(side='right', padx=8)

        # Treeview
        cols = ('#', 'Equipo A', 'País A', 'Equipo B', 'País B',
                'Logo A', 'Logo B', 'Fondo')
        widths = (36, 185, 95, 185, 95, 135, 135, 70)

        tree_frame = tk.Frame(frame)
        tree_frame.pack(fill='both', expand=True)

        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                   show='headings', height=12)
        for col, w in zip(cols, widths):
            anchor = 'center' if col in ('#', 'Logo A', 'Logo B', 'Fondo') else 'w'
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor=anchor, stretch=False)

        # Row colour tags
        self._tree.tag_configure('ready',     foreground='#1b5e20')
        self._tree.tag_configure('generated', background='#e8f5e9', foreground='#1b5e20')
        self._tree.tag_configure('failed',    background='#ffebee', foreground='#b71c1c')
        self._tree.tag_configure('warning',   foreground='#e65100')
        self._tree.tag_configure('error',     foreground='#c62828')
        self._tree.tag_configure('pending',   foreground='#757575')

        vsb = ttk.Scrollbar(tree_frame, orient='vertical',
                             command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient='horizontal',
                             command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

    # ── 5. Bottom (generate + progress + log) ─────────────────────────────

    def _build_bottom_section(self):
        frame = tk.Frame(self)
        frame.pack(fill='x', padx=10, pady=4)

        btn_row = tk.Frame(frame)
        btn_row.pack(fill='x')

        self._gen_btn = tk.Button(
            btn_row, text='▶  GENERAR TODO',
            command=self._generate_all,
            bg='#1b5e20', fg='white',
            font=('Arial', 11, 'bold'),
            height=2, padx=20)
        self._gen_btn.pack(side='left', padx=4)

        self._progress_var = tk.DoubleVar()
        pb = ttk.Progressbar(btn_row, variable=self._progress_var,
                             maximum=100, length=320)
        pb.pack(side='left', padx=8, fill='x', expand=True)

        self._pct_label = tk.Label(btn_row, text='0 %', width=6)
        self._pct_label.pack(side='left')

        # Log
        log_frame = tk.LabelFrame(self, text='Log', padx=5, pady=4)
        log_frame.pack(fill='x', padx=10, pady=(0, 6))

        self._log = tk.Text(log_frame, height=5, state='disabled',
                            bg='#fafafa', fg='#333', font=('Courier', 9))
        log_sb = tk.Scrollbar(log_frame, command=self._log.yview)
        self._log.configure(yscrollcommand=log_sb.set)
        self._log.pack(side='left', fill='x', expand=True)
        log_sb.pack(side='right', fill='y')

    # ══════════════════════════════════════════════════════════════════════
    # ACTIONS
    # ══════════════════════════════════════════════════════════════════════

    # ── Excel ──────────────────────────────────────────────────────────────

    def _load_excel(self):
        path = filedialog.askopenfilename(
            title='Seleccionar Excel de Enfrentamientos',
            filetypes=[('Excel', '*.xlsx *.xls')])
        if not path:
            return
        try:
            self.matches = load_matches(path)
            self._excel_label.config(
                text=f"{os.path.basename(path)}  ({len(self.matches)} enfrentamientos)",
                fg='#1565c0')
            self._rebuild_tree()
            self._log_msg(f'✓ Cargado: {len(self.matches)} enfrentamientos '
                          f'desde {os.path.basename(path)}')
        except Exception as exc:
            messagebox.showerror('Error al cargar Excel', str(exc))

    # ── Background ─────────────────────────────────────────────────────────

    def _pick_global_bg(self):
        path = filedialog.askopenfilename(
            title='Imagen de fondo global',
            filetypes=[('Imágenes', '*.jpg *.jpeg *.png')])
        if not path:
            return
        self.global_background = path
        self._global_bg_label.config(
            text=os.path.basename(path), fg='#2e7d32')
        if self.bg_mode.get() == 'global':
            for m in self.matches:
                m['background'] = path
            self._rebuild_tree()
        self._log_msg(f'✓ Fondo global: {os.path.basename(path)}')

    def _on_bg_mode(self):
        mode = self.bg_mode.get()
        if mode == 'global':
            self._per_match_btn.config(state='disabled')
            if self.global_background:
                for m in self.matches:
                    m['background'] = self.global_background
                self._rebuild_tree()
        else:
            self._per_match_btn.config(state='normal')

    def _pick_per_match_bg(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning('Sin selección',
                                   'Selecciona un enfrentamiento en la tabla.')
            return
        path = filedialog.askopenfilename(
            title='Fondo para el enfrentamiento seleccionado',
            filetypes=[('Imágenes', '*.jpg *.jpeg *.png')])
        if not path:
            return
        for iid in sel:
            idx = self._iid_to_idx(iid)
            if idx is not None:
                self.matches[idx]['background'] = path
        self._rebuild_tree()
        self._log_msg(f'✓ Fondo asignado: {os.path.basename(path)}')

    # ── Manual logo resolution ─────────────────────────────────────────────

    def _manual_logo(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning('Sin selección',
                                   'Selecciona un enfrentamiento en la tabla.')
            return
        if len(sel) > 1:
            messagebox.showwarning('Selección múltiple',
                                   'Selecciona sólo un enfrentamiento a la vez.')
            return
        idx = self._iid_to_idx(sel[0])
        if idx is not None:
            _ManualLogoDialog(self, idx, self.matches[idx],
                              CACHE_DIR, self._on_manual_logo_saved)

    def _on_manual_logo_saved(self, match_idx):
        self._update_row(match_idx)
        self._update_counts()

    # ── Logo fetch (background thread) ────────────────────────────────────

    def _fetch_logos(self):
        if not self.matches:
            messagebox.showwarning('Sin datos',
                                   'Primero carga un Excel con enfrentamientos.')
            return
        if self._busy:
            messagebox.showwarning('Ocupado',
                                   'Ya hay una operación en curso. Espera.')
            return
        self._set_busy(True)
        self._log_msg('Iniciando búsqueda de logos…')
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        teams_cache = {}   # (team_key, country_key) → result tuple
        total = len(self.matches)

        for i, match in enumerate(self.matches):
            for side in ('a', 'b'):
                team    = match[f'equipo_{side}']
                country = match[f'pais_{side}']
                key     = (team.lower().strip(), country.lower().strip())

                if key not in teams_cache:
                    self._queue.put(('log', f'  Buscando: {team} ({country})…'))
                    try:
                        path, status, url, size = fetch_logo(
                            team, country, CACHE_DIR)
                    except Exception as exc:
                        path, status, url, size = None, 'ERROR', None, None
                        self._queue.put(('log', f'  ⚠ Error: {exc}'))
                    teams_cache[key] = (path, status, url, size)

                path, status, url, size = teams_cache[key]
                match[f'logo_{side}']        = path
                match[f'logo_{side}_status'] = status or 'NOT_FOUND'
                match[f'logo_{side}_url']    = url
                match[f'logo_{side}_size']   = size
                match[f'logo_{side}_source'] = (
                    'wiki'     if status and 'WIKI' in status else
                    'sportsdb' if status and 'SPORTSDB' in status else
                    'manual'   if status == 'MANUAL_OK' else
                    'unknown'
                )

            pct = int((i + 1) / total * 100)
            self._queue.put(('progress', pct))
            self._queue.put(('update_row', i))

        self._queue.put(('log', '✓ Búsqueda de logos completada.'))
        self._queue.put(('done_fetch', None))

    # ── Generate (background thread) ──────────────────────────────────────

    def _generate_all(self):
        if not self.matches:
            messagebox.showwarning('Sin datos',
                                   'Primero carga un Excel con enfrentamientos.')
            return
        if self._busy:
            messagebox.showwarning('Ocupado',
                                   'Ya hay una operación en curso. Espera.')
            return
        if self.bg_mode.get() == 'global' and not self.global_background:
            messagebox.showerror('Sin fondo',
                                 'Selecciona una imagen de fondo global primero.')
            return

        self._set_busy(True)
        self._log_msg('Iniciando generación de imágenes…')

        ts       = datetime.now().strftime('%Y%m%d-%H%M%S')
        run_dir  = os.path.join(OUTPUT_DIR, ts)
        imgs_dir = os.path.join(run_dir, 'images')
        os.makedirs(imgs_dir, exist_ok=True)

        threading.Thread(
            target=self._generate_worker,
            args=(imgs_dir, run_dir),
            daemon=True).start()

    def _generate_worker(self, imgs_dir, run_dir):
        # Ensure global background is applied
        if self.bg_mode.get() == 'global' and self.global_background:
            for m in self.matches:
                if not m.get('background'):
                    m['background'] = self.global_background

        add_outline   = self.add_outline.get()
        outline_width = self.outline_width.get()
        auto_enhance  = self.auto_enhance.get()
        total         = len(self.matches)

        for i, match in enumerate(self.matches):
            self._queue.put(
                ('log', f"Generando: {match['equipo_a']} vs {match['equipo_b']}…"))

            problems = []
            if not match.get('logo_a'):
                problems.append(f"Logo A ausente ({match.get('logo_a_status', '?')})")
            if not match.get('logo_b'):
                problems.append(f"Logo B ausente ({match.get('logo_b_status', '?')})")
            if not match.get('background'):
                problems.append('Sin imagen de fondo')

            if problems:
                match['match_status'] = 'FAILED'
                match['error']        = '; '.join(problems)
                self._queue.put(('log', f"  ✗ Saltado: {match['error']}"))
            else:
                try:
                    outputs = generate_single_enfrentamiento(
                        match, imgs_dir,
                        add_outline=add_outline,
                        outline_width=outline_width,
                        auto_enhance=auto_enhance,
                    )
                    match['match_status'] = 'GENERATED'
                    match['output_1920']  = outputs.get('1920x1080')
                    match['output_3840']  = outputs.get('3840x2160')
                    match['output_480']   = outputs.get('480x720')
                    self._queue.put(('log', '  ✓ OK'))
                except Exception as exc:
                    match['match_status'] = 'FAILED'
                    match['error']        = str(exc)
                    self._queue.put(('log', f'  ✗ Error: {exc}'))

            pct = int((i + 1) / total * 100)
            self._queue.put(('progress', pct))
            self._queue.put(('update_row', i))

        # Report
        try:
            rpt = generate_report(run_dir, self.matches)
            self._queue.put(('log', f'✓ Reporte: {rpt}'))
        except Exception as exc:
            self._queue.put(('log', f'⚠ Error al generar reporte: {exc}'))

        self._queue.put(('done_generate', run_dir))

    # ══════════════════════════════════════════════════════════════════════
    # TREEVIEW HELPERS
    # ══════════════════════════════════════════════════════════════════════

    def _rebuild_tree(self):
        self._tree.delete(*self._tree.get_children())
        for i, m in enumerate(self.matches):
            self._insert_row(i, m)
        self._update_counts()

    def _insert_row(self, idx, match):
        la = _status_to_label(match.get('logo_a_status', 'PENDING'))
        lb = _status_to_label(match.get('logo_b_status', 'PENDING'))
        bg = '✓' if match.get('background') else '–'
        tag = _row_tag(
            match.get('logo_a_status', ''),
            match.get('logo_b_status', ''),
            match.get('match_status', ''),
            bool(match.get('background')),
        )
        self._tree.insert('', 'end', iid=str(idx), tags=(tag,),
                          values=(idx + 1,
                                  match['equipo_a'], match['pais_a'],
                                  match['equipo_b'], match['pais_b'],
                                  la, lb, bg))

    def _update_row(self, idx):
        if idx >= len(self.matches):
            return
        match = self.matches[idx]
        iid   = str(idx)
        if not self._tree.exists(iid):
            return
        la  = _status_to_label(match.get('logo_a_status', 'PENDING'))
        lb  = _status_to_label(match.get('logo_b_status', 'PENDING'))
        bg  = '✓' if match.get('background') else '–'
        tag = _row_tag(
            match.get('logo_a_status', ''),
            match.get('logo_b_status', ''),
            match.get('match_status', ''),
            bool(match.get('background')),
        )
        self._tree.item(iid,
                        values=(idx + 1,
                                match['equipo_a'], match['pais_a'],
                                match['equipo_b'], match['pais_b'],
                                la, lb, bg),
                        tags=(tag,))

    def _update_counts(self):
        if not self.matches:
            self._count_label.config(text='')
            return
        total  = len(self.matches)
        ok_a   = sum(1 for m in self.matches
                     if m.get('logo_a_status', '').startswith('OK')
                     or m.get('logo_a_status') in ('MANUAL_OK', 'CACHED'))
        ok_b   = sum(1 for m in self.matches
                     if m.get('logo_b_status', '').startswith('OK')
                     or m.get('logo_b_status') in ('MANUAL_OK', 'CACHED'))
        gen    = sum(1 for m in self.matches if m.get('match_status') == 'GENERATED')
        self._count_label.config(
            text=f'{total} partidos  |  Logos OK: {ok_a+ok_b}/{total*2}  '
                 f'|  Generados: {gen}/{total}')

    # ══════════════════════════════════════════════════════════════════════
    # QUEUE POLLING (thread-safe UI updates)
    # ══════════════════════════════════════════════════════════════════════

    def _poll(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == 'log':
                    self._log_msg(payload)
                elif kind == 'progress':
                    self._set_progress(payload)
                elif kind == 'update_row':
                    self._update_row(payload)
                    self._update_counts()
                elif kind == 'done_fetch':
                    self._set_busy(False)
                    self._rebuild_tree()
                    self._log_msg('Logos actualizados.')
                elif kind == 'done_generate':
                    self._set_busy(False)
                    self._rebuild_tree()
                    run_dir   = payload
                    generated = sum(1 for m in self.matches
                                    if m.get('match_status') == 'GENERATED')
                    failed    = sum(1 for m in self.matches
                                    if m.get('match_status') == 'FAILED')
                    parts = [f'✅  {generated} imágenes generadas.']
                    if failed:
                        parts.append(f'❌  {failed} fallidas.')
                    parts.append(f'\nSalida: {run_dir}')
                    messagebox.showinfo('Generación completa', '\n'.join(parts))
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ══════════════════════════════════════════════════════════════════════
    # SMALL UTILITIES
    # ══════════════════════════════════════════════════════════════════════

    def _iid_to_idx(self, iid):
        try:
            return int(iid)
        except (ValueError, TypeError):
            return None

    def _set_busy(self, busy):
        self._busy = busy
        self._gen_btn.config(state='disabled' if busy else 'normal')

    def _log_msg(self, text):
        self._log.config(state='normal')
        self._log.insert('end', text + '\n')
        self._log.see('end')
        self._log.config(state='disabled')

    def _set_progress(self, pct):
        self._progress_var.set(pct)
        self._pct_label.config(text=f'{pct} %')


# ═══════════════════════════════════════════════════════════════════════════════

class _ManualLogoDialog(tk.Toplevel):
    """Modal dialog to manually assign logos to one match."""

    def __init__(self, parent, match_idx, match, cache_dir, on_saved):
        super().__init__(parent)
        self.title('Resolver Logos Manualmente')
        self.geometry('520x230')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._match_idx = match_idx
        self._match     = match
        self._cache_dir = cache_dir
        self._on_saved  = on_saved

        tk.Label(self,
                 text=f"{match['equipo_a']}  vs  {match['equipo_b']}",
                 font=('Arial', 12, 'bold')).pack(pady=12)

        for side_label, side_key in (('A', 'a'), ('B', 'b')):
            team   = match[f'equipo_{side_key}']
            status = _status_to_label(match.get(f'logo_{side_key}_status', 'PENDING'))

            row = tk.Frame(self)
            row.pack(fill='x', padx=20, pady=5)

            tk.Label(row, text=f'Equipo {side_label}: {team}',
                     width=30, anchor='w').pack(side='left')
            tk.Label(row, text=f'[{status}]',
                     fg='gray', width=16).pack(side='left')
            tk.Button(row, text=f'Elegir logo {side_label}…',
                      command=lambda k=side_key, t=team: self._pick(k, t),
                      padx=6).pack(side='right')

        tk.Button(self, text='Cerrar', command=self.destroy,
                  padx=12).pack(pady=15)

    def _pick(self, side_key, team_name):
        path = filedialog.askopenfilename(
            parent=self,
            title=f'Seleccionar logo para {team_name}',
            filetypes=[('Imágenes', '*.png *.jpg *.jpeg *.svg')])
        if not path:
            return

        # Copy file into manual cache
        slug = slugify(team_name)
        ext  = os.path.splitext(path)[1].lower()
        dest = os.path.join(self._cache_dir, 'manual', f"{slug}{ext}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)

        # Save meta
        meta = {
            'status': 'MANUAL_OK',
            'url': path,
            'source': 'manual',
            'size': None,
            'downloaded_at': datetime.now().isoformat(),
        }
        with open(dest + '.json', 'w', encoding='utf-8') as fh:
            json.dump(meta, fh, indent=2)

        self._match[f'logo_{side_key}']        = dest
        self._match[f'logo_{side_key}_status'] = 'MANUAL_OK'
        self._match[f'logo_{side_key}_source'] = 'manual'
        self._match[f'logo_{side_key}_url']    = path

        self._on_saved(self._match_idx)


# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    app = BatchApp()
    app.mainloop()
