"""
generator.py
Genera imágenes de enfrentamientos en múltiples resoluciones.
Basado en la lógica de app_generadora.py.

Resoluciones:
  • 1920×1080  (landscape HD)
  • 3840×2160  (landscape 4K)
  •  480×720   (portrait / story)
"""

import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ── Constantes ─────────────────────────────────────────────────────────────────
RESOLUTIONS = [
    ("1920x1080", 1920, 1080, "landscape"),
    ("3840x2160", 3840, 2160, "landscape"),
    ("480x720",    480,  720, "portrait"),
]

# Proporción del logo respecto al ancho del canvas (landscape)
LOGO_WIDTH_RATIO = 0.28
# Proporción del logo respecto al ancho del canvas (portrait)
LOGO_WIDTH_RATIO_PORTRAIT = 0.38

# Posición vertical del logo (centro relativo al alto del canvas)
LOGO_CENTER_Y_RATIO = 0.50

# Posición horizontal del logo A y B (respecto al ancho del canvas)
LOGO_A_CENTER_X_RATIO = 0.20
LOGO_B_CENTER_X_RATIO = 0.80

# Para portrait, los logos van lado a lado en la parte superior
LOGO_A_CENTER_X_PORTRAIT = 0.25
LOGO_B_CENTER_X_PORTRAIT = 0.75
LOGO_CENTER_Y_PORTRAIT = 0.38

# "VS" text
VS_TEXT = "VS"
VS_COLOR = (255, 255, 255)
VS_STROKE_COLOR = (0, 0, 0)

# Fuentes (Pillow busca en sistema; fallback a default)
_FONT_PATHS = [
    "assets/fonts/Roboto-BlackItalic.ttf",
    "assets/fonts/Roboto-Bold.ttf",
    "assets/fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for fp in _FONT_PATHS:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _slugify_filename(text: str) -> str:
    """Genera un nombre de archivo seguro."""
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "_", text.strip())
    return text[:60]


def _load_logo(path: Path | str) -> Image.Image:
    """Carga un logo (SVG o raster) como imagen RGBA."""
    p = Path(path)
    if p.suffix.lower() == ".svg":
        try:
            import cairosvg
            png_data = cairosvg.svg2png(
                url=str(p),
                output_width=1024,
                output_height=1024,
            )
            return Image.open(io.BytesIO(png_data)).convert("RGBA")
        except ImportError:
            raise RuntimeError(
                "cairosvg es necesario para renderizar SVG. "
                "Instala con: pip install cairosvg"
            )
    else:
        return Image.open(p).convert("RGBA")


def _add_white_outline(
    img: Image.Image, outline_width: int = 8
) -> Image.Image:
    """
    Agrega un contorno blanco alrededor del área opaca del logo.
    """
    if outline_width <= 0:
        return img
    w, h = img.size
    # Expandir canvas para el contorno
    pad = outline_width * 2
    canvas = Image.new("RGBA", (w + pad, h + pad), (0, 0, 0, 0))

    # Crear máscara de contorno expandida
    alpha = img.split()[3]
    outline_layer = Image.new("RGBA", (w + pad, h + pad), (0, 0, 0, 0))
    # Pegar múltiples offsets para simular contorno
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx * dx + dy * dy <= outline_width * outline_width:
                tmp = Image.new("RGBA", (w + pad, h + pad), (255, 255, 255, 0))
                mask = alpha.point(lambda p: 255 if p > 10 else 0)
                tmp.paste((255, 255, 255, 255), (outline_width + dx, outline_width + dy), mask)
                outline_layer = Image.alpha_composite(outline_layer, tmp)

    canvas = Image.alpha_composite(canvas, outline_layer)
    canvas.paste(img, (outline_width, outline_width), img)
    return canvas


def _fit_logo(
    logo: Image.Image,
    target_w: int,
    target_h: int,
) -> Image.Image:
    """Redimensiona el logo para que quepa en target_w×target_h conservando aspecto."""
    lw, lh = logo.size
    ratio = min(target_w / lw, target_h / lh)
    new_w = max(1, int(lw * ratio))
    new_h = max(1, int(lh * ratio))
    return logo.resize((new_w, new_h), Image.LANCZOS)


def _compose_image(
    background: Image.Image,
    logo_a: Image.Image,
    logo_b: Image.Image,
    width: int,
    height: int,
    orientation: str,
    team_a: str,
    team_b: str,
    outline: bool = False,
    outline_width: int = 8,
) -> Image.Image:
    """Compone la imagen final para una resolución dada."""
    # Redimensionar y recortar fondo
    bg = background.convert("RGB").resize(
        (width, height), Image.LANCZOS
    )
    canvas = bg.convert("RGBA")

    if orientation == "portrait":
        logo_target_w = int(width * LOGO_WIDTH_RATIO_PORTRAIT)
        cx_a = int(width * LOGO_A_CENTER_X_PORTRAIT)
        cx_b = int(width * LOGO_B_CENTER_X_PORTRAIT)
        cy = int(height * LOGO_CENTER_Y_PORTRAIT)
    else:
        logo_target_w = int(width * LOGO_WIDTH_RATIO)
        cx_a = int(width * LOGO_A_CENTER_X_RATIO)
        cx_b = int(width * LOGO_B_CENTER_X_RATIO)
        cy = int(height * LOGO_CENTER_Y_RATIO)

    logo_target_h = logo_target_w  # cuadrado máximo

    # Aplicar contorno si corresponde
    if outline:
        ow = max(1, int(outline_width * width / 1920))
        logo_a = _add_white_outline(logo_a, ow)
        logo_b = _add_white_outline(logo_b, ow)

    # Redimensionar logos
    logo_a_fit = _fit_logo(logo_a, logo_target_w, logo_target_h)
    logo_b_fit = _fit_logo(logo_b, logo_target_w, logo_target_h)

    # Pegar logo A
    la_w, la_h = logo_a_fit.size
    canvas.paste(logo_a_fit, (cx_a - la_w // 2, cy - la_h // 2), logo_a_fit)

    # Pegar logo B
    lb_w, lb_h = logo_b_fit.size
    canvas.paste(logo_b_fit, (cx_b - lb_w // 2, cy - lb_h // 2), logo_b_fit)

    # Texto "VS"
    vs_size = max(20, int(width * 0.06))
    font = _load_font(vs_size)
    draw = ImageDraw.Draw(canvas)

    cx_mid = width // 2
    cy_mid = cy

    # bbox of the text (Pillow >= 10.0 always has textbbox)
    bbox = draw.textbbox((0, 0), VS_TEXT, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    tx = cx_mid - tw // 2
    ty = cy_mid - th // 2

    stroke_w = max(1, vs_size // 15)
    draw.text(
        (tx, ty),
        VS_TEXT,
        font=font,
        fill=VS_COLOR,
        stroke_width=stroke_w,
        stroke_fill=VS_STROKE_COLOR,
    )

    # Nombres de equipos (texto en la parte inferior o bajo logos)
    name_size = max(12, int(width * 0.022))
    name_font = _load_font(name_size)

    if orientation == "portrait":
        ty_name = cy + logo_target_h // 2 + int(height * 0.02)
    else:
        ty_name = cy + logo_target_h // 2 + int(height * 0.02)

    for team_name, cx_team in [(team_a, cx_a), (team_b, cx_b)]:
        nb = draw.textbbox((0, 0), team_name, font=name_font)
        nw = nb[2] - nb[0]
        nx = cx_team - nw // 2
        nstroke = max(1, name_size // 12)
        draw.text(
            (nx, ty_name),
            team_name,
            font=name_font,
            fill=(255, 255, 255),
            stroke_width=nstroke,
            stroke_fill=(0, 0, 0),
        )

    return canvas.convert("RGB")


def generate_matchup(
    match: dict,
    output_dir: Path | str,
    outline: bool = False,
    outline_width: int = 8,
    auto_enhance: bool = False,
) -> dict:
    """
    Genera imágenes para un enfrentamiento en 3 resoluciones.

    Parámetros:
        match: dict con keys: equipo_a, pais_a, equipo_b, pais_b,
               logo_a_path, logo_b_path, background_path.
        output_dir: carpeta raíz de salida (se creará si no existe).
        outline: aplicar contorno blanco a logos.
        outline_width: grosor del contorno en píxeles (para 1920px).
        auto_enhance: mejorar automáticamente el contraste/saturación del fondo.

    Retorna:
        dict con keys: success, output_1920, output_3840, output_480, error.
    """
    output_dir = Path(output_dir)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "success": False,
        "output_1920": None,
        "output_3840": None,
        "output_480": None,
        "error": None,
    }

    # ── Cargar assets ────────────────────────────────────────────────────
    try:
        logo_a = _load_logo(match["logo_a_path"])
    except Exception as e:
        result["error"] = f"Error cargando logo A: {e}"
        return result

    try:
        logo_b = _load_logo(match["logo_b_path"])
    except Exception as e:
        result["error"] = f"Error cargando logo B: {e}"
        return result

    try:
        bg = Image.open(match["background_path"]).convert("RGBA")
    except Exception as e:
        result["error"] = f"Error cargando fondo: {e}"
        return result

    if auto_enhance:
        bg_rgb = bg.convert("RGB")
        bg_rgb = ImageEnhance.Contrast(bg_rgb).enhance(1.15)
        bg_rgb = ImageEnhance.Color(bg_rgb).enhance(1.10)
        bg = bg_rgb.convert("RGBA")

    team_a = match.get("equipo_a", "Equipo A")
    team_b = match.get("equipo_b", "Equipo B")

    slug_a = _slugify_filename(team_a)
    slug_b = _slugify_filename(team_b)
    base_name = f"{slug_a}_vs_{slug_b}"

    res_keys = {
        "1920x1080": "output_1920",
        "3840x2160": "output_3840",
        "480x720":   "output_480",
    }

    # ── Generar cada resolución ──────────────────────────────────────────
    for res_label, w, h, orientation in RESOLUTIONS:
        try:
            img = _compose_image(
                background=bg,
                logo_a=logo_a,
                logo_b=logo_b,
                width=w,
                height=h,
                orientation=orientation,
                team_a=team_a,
                team_b=team_b,
                outline=outline,
                outline_width=outline_width,
            )
            filename = f"{base_name}_{res_label}.jpg"
            out_path = images_dir / filename
            img.save(out_path, "JPEG", quality=95, optimize=True)
            result[res_keys[res_label]] = str(out_path)
        except Exception as e:
            result["error"] = (result.get("error") or "") + f"[{res_label}] {e}; "

    if any(result[k] for k in res_keys.values()):
        result["success"] = True

    return result
