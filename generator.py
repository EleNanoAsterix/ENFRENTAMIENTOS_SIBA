"""
generator.py – Image generation logic extracted from app_generadora.py.

Provides standalone functions for loading logos, resizing with optional
white-outline effect, auto-enhancing backgrounds, and compositing the
final "vs." match images in three resolutions.
"""

import io
import os
import re

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance

try:
    import cairosvg
    _CAIROSVG = True
except Exception:
    _CAIROSVG = False

# ── Resolutions ───────────────────────────────────────────────────────────────
# (width, height, logo_a_centre, logo_b_centre, logo_max_px, font_px, label)
RESOLUTIONS = [
    (1920, 1080, (476,  666), (1440,  666), 450,                      130,                      '1920x1080'),
    (3840, 2160, (952, 1332), (2880, 1332), int(450 * 3840 / 1920),   int(130 * 3840 / 1920),   '3840x2160'),
    (480,   720, (120,  230), (360,   515), 177,                       60,                       '480x720'),
]

# Ordered list of font files to try (most preferred first)
_FONT_PATHS = [
    'Roboto-BlackItalic.ttf',
    'Roboto-Black.ttf',
    'Roboto-BoldItalic.ttf',
    'Impact-Italic.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
]


# ── Public helpers ─────────────────────────────────────────────────────────────

def load_and_convert_logo(file_path):
    """Load *file_path* (SVG or raster) and return an RGBA :class:`PIL.Image`."""
    if file_path.lower().endswith('.svg'):
        if not _CAIROSVG:
            raise RuntimeError('cairosvg no está disponible para procesar SVG.')
        try:
            png_data = cairosvg.svg2png(url=file_path)
            return Image.open(io.BytesIO(png_data)).convert('RGBA')
        except Exception:
            # Try again after cleaning known broken entity references
            with open(file_path, 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()
            cleaned = content.replace('&ns_extend;', '').replace('&ns_ai;', '')
            try:
                png_data = cairosvg.svg2png(bytestring=cleaned.encode('utf-8'))
                return Image.open(io.BytesIO(png_data)).convert('RGBA')
            except Exception:
                raise RuntimeError(f'No se pudo procesar el SVG: {file_path}')
    else:
        return Image.open(file_path).convert('RGBA')


def resize_logo(logo_image, max_size=450, add_outline=False, outline_width=3):
    """Resize *logo_image* to fit within *max_size* px, optionally adding a
    white glow/outline using the super-sampled technique from app_generadora.py.
    """
    w, h = logo_image.size
    if w >= h:
        new_w, new_h = max_size, max(1, int(h * max_size / w))
    else:
        new_h, new_w = max_size, max(1, int(w * max_size / h))

    logo_resized = logo_image.resize((new_w, new_h), Image.LANCZOS)

    if not add_outline:
        return logo_resized

    scale = 4
    temp = logo_resized.resize((new_w * scale, new_h * scale), Image.LANCZOS)
    alpha = temp.split()[-1] if temp.mode == 'RGBA' else Image.new('L', temp.size, 255)

    blur_r = outline_width * scale
    padding = int(outline_width * scale * 2.5) + blur_r * 2

    exp_w = temp.width + 2 * padding
    exp_h = temp.height + 2 * padding
    exp_alpha = Image.new('L', (exp_w, exp_h), 0)
    exp_alpha.paste(alpha, ((exp_w - alpha.width) // 2, (exp_h - alpha.height) // 2))

    blurred = exp_alpha.filter(ImageFilter.MaxFilter(3)).filter(
        ImageFilter.GaussianBlur(blur_r)
    )

    result = Image.new('RGBA', (exp_w, exp_h), (0, 0, 0, 0))
    result.paste((255, 255, 255), (0, 0), mask=blurred)
    result.paste(temp, ((exp_w - temp.width) // 2, (exp_h - temp.height) // 2), temp)

    return result.resize((exp_w // scale, exp_h // scale), Image.LANCZOS)


def auto_enhance_background(img):
    """Apply a mild set of enhancements to *img* (RGB PIL Image)."""
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img = ImageOps.equalize(img)
    img = ImageEnhance.Contrast(img).enhance(1.1)
    img = ImageEnhance.Brightness(img).enhance(1.05)
    img = ImageEnhance.Color(img).enhance(1.1)
    img = ImageEnhance.Sharpness(img).enhance(1.1)
    return img


def generate_single_enfrentamiento(match, output_dir,
                                   add_outline=False,
                                   outline_width=3,
                                   auto_enhance=False):
    """Generate match images in all three resolutions.

    Args:
        match:         dict with keys ``equipo_a``, ``equipo_b``,
                       ``logo_a``, ``logo_b``, ``background``.
        output_dir:    directory where JPEG files are saved.
        add_outline:   add white glow/outline to logos.
        outline_width: outline thickness in logical pixels.
        auto_enhance:  apply auto-enhancement to background.

    Returns:
        dict mapping resolution label → saved file path,
        e.g. ``{'1920x1080': '/path/…', '3840x2160': …, '480x720': …}``.
    """
    equipo_a = match['equipo_a']
    equipo_b = match['equipo_b']
    background_path = match['background']
    logo_a_path = match['logo_a']
    logo_b_path = match['logo_b']

    os.makedirs(output_dir, exist_ok=True)
    outputs = {}

    for (width, height,
         logo_a_pos, logo_b_pos,
         logo_size, font_size, res_str) in RESOLUTIONS:

        # ── Background ──────────────────────────────────────────────────────
        bg = Image.open(background_path).convert('RGB')
        bw, bh = bg.size
        aspect_bg  = bw / bh
        aspect_out = width / height

        if aspect_bg > aspect_out:
            new_w = int(height * aspect_bg)
            new_h = height
        else:
            new_w = width
            new_h = int(width / aspect_bg)

        bg = bg.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - width) // 2
        top  = (new_h - height) // 2
        bg = bg.crop((left, top, left + width, top + height))

        blur_r = {1920: 11.3, 3840: 20.0, 480: 8.1}.get(width, 10.0)
        bg = bg.filter(ImageFilter.GaussianBlur(blur_r))

        if auto_enhance:
            bg = auto_enhance_background(bg)

        image = bg
        draw  = ImageDraw.Draw(image)

        # ── Logos ────────────────────────────────────────────────────────────
        logo_a = load_and_convert_logo(logo_a_path)
        logo_a = resize_logo(logo_a, logo_size, add_outline, outline_width)
        image.paste(logo_a,
                    (logo_a_pos[0] - logo_a.width  // 2,
                     logo_a_pos[1] - logo_a.height // 2),
                    logo_a)

        logo_b = load_and_convert_logo(logo_b_path)
        logo_b = resize_logo(logo_b, logo_size, add_outline, outline_width)
        image.paste(logo_b,
                    (logo_b_pos[0] - logo_b.width  // 2,
                     logo_b_pos[1] - logo_b.height // 2),
                    logo_b)

        # ── "VS." text ───────────────────────────────────────────────────────
        font = _load_font(font_size)
        text = 'VS.'
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        cx = (width  - tw) // 2
        cy = (height - th) // 2
        offset = int(height * 0.02) if width == 480 else int(height * 0.05)
        draw.text((cx, cy + offset), text, fill='white', font=font)

        # ── Save ─────────────────────────────────────────────────────────────
        filename  = f"{_safe_name(equipo_a)} vs {_safe_name(equipo_b)} - {res_str}.jpg"
        save_path = os.path.join(output_dir, filename)
        image.convert('RGB').save(save_path, 'JPEG', quality=97)
        outputs[res_str] = save_path

    return outputs


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_font(size):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _safe_name(name):
    """Strip characters that are illegal in common filesystem filenames."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()
