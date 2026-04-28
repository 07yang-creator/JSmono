"""
generate_flyer.py  —  Justsalemono  (Template 1)
─────────────────────────────────────────────────────────────
A4 landscape.  Fixed-geometry layout — ALL box sizes are constants.
Auto-fitting = font-size only, never box-size.

LEFT COLUMN (≈24.5% IW)
  ┌──────────────────────┐  ← CTOP
  │  Zone 3: prop name   │
  │──────────────────────│  ← Z3_BOT / Z2_TOP
  │  Zone 2: type pill   │  NAV_H (= TOP_H - PRICE_H - ST_H)
  │──────────────────────│  ← Z2_BOT / Z1_TOP
  │  Zone 1: address     │
  ├──────────────────────┤  ← nav_y = BAND_BOT + PRICE_H + ST_H
  │  Station strip       │  ST_H (14mm fixed)
  ├──────────────────────┤  ← BAND_BOT + PRICE_H
  │  Price strip         │  PRICE_H (20mm fixed)
  └──────────────────────┘  ← BAND_BOT

RIGHT AREA (≈75.5% IW)  — Q1 left half / Q2 right half
  ┌─────────────┬─────────────┐  ← CTOP
  │  K1 photo   │  K5 map     │  TOP_H (48% of CONTENT_H)
  ├─────────────┼─────────────┤  ← BAND_BOT
  │  H/I nearby │  K2 floor   │  MID_H (52%)
  └─────────────┴─────────────┘  ← CBOT

FOOTER  (34mm fixed, IW width)
  Logo | Name | Info | Contact | Yellow
"""

import json, sys, os, io, math, base64
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from http.server import BaseHTTPRequestHandler
try:
    from PIL import Image, ImageOps
    _PIL_OK = True
except Exception:
    _PIL_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# PHOTO_FIT_SCHEMA — single source of truth for how each photo slot is fitted
# into its frame. 'cover'   = scale to fill the rect, center-crop the overflow
#                            (best for exterior / interior / scenery photos).
#                'contain' = scale to fit inside the rect with letterbox bg
#                            (used for floor plans, maps, diagrams — anything
#                            where cropping would destroy information).
# Defaults to 'cover' when a slot is not listed.
# ─────────────────────────────────────────────────────────────────────────────
PHOTO_FIT_SCHEMA = {
    # Template 1, Variant A (Q1/Q2 quad split)
    ('1', 'A', 'k2'): 'contain',  # Q2-bottom: floor plan
    ('1', 'A', 'k5'): 'contain',  # Q2-top:    map
    # Template 1, Variant B (flex grid 2x2 — K1/K2/K3 exteriors, K4 = floor plan / map)
    ('1', 'B', 'k4'): 'contain',  # 間取り / 地図 — floor plan or map slot
    # Template 2, Variant A (sample-accurate layout)
    ('2', 'A', 'k2'): 'contain',  # floor plan (largest tile, middle row)
    ('2', 'A', 'k4'): 'contain',  # map tile (top-right)
    # Template 2, Variant B
    ('2', 'B', 'k2'): 'contain',  # floor plan (top-right)
}
def fit_mode(template_id, variant, slot_key):
    """Look up the per-slot fit mode. Falls back to 'cover'."""
    s = (slot_key or '').lower().replace('image', '')
    return PHOTO_FIT_SCHEMA.get((str(template_id), str(variant or 'A'), s), 'cover')

# ── Font ──────────────────────────────────────────────────────────────────────
_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts')

def _resolve_font():
    for p in [
        os.environ.get('FONT_PATH', ''),
        os.path.join(_FONT_DIR, 'DroidSansFallbackFull.ttf'),
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError('DroidSansFallbackFull.ttf not found.')

def _resolve_noto(bold=False):
    """Return path to Noto Sans JP Regular/Bold, or None if not available."""
    suffix = 'Bold' if bold else 'Regular'
    for p in [
        os.environ.get('NOTO_BOLD_PATH' if bold else 'NOTO_REGULAR_PATH', ''),
        os.path.join(_FONT_DIR, f'NotoSansJP-{suffix}.ttf'),
    ]:
        if p and os.path.exists(p) and os.path.getsize(p) > 100_000:
            return p
    return None

JP_FONT      = 'JP'          # DroidSansFallback — full document body
LA_FONT      = 'Helvetica'
LA_BOLD      = 'Helvetica-Bold'
# Noto Sans JP — nav box (upper-left) optional font; registered lazily per request
NOTO_REG     = 'NotoJP'
NOTO_BOLD_F  = 'NotoJP-Bold'
_noto_available = False      # updated at module load below

pdfmetrics.registerFont(TTFont(JP_FONT, _resolve_font()))

# Register Noto Sans JP if the font files exist
_noto_reg_path  = _resolve_noto(bold=False)
_noto_bold_path = _resolve_noto(bold=True)
if _noto_reg_path and _noto_bold_path:
    pdfmetrics.registerFont(TTFont(NOTO_REG,    _noto_reg_path))
    pdfmetrics.registerFont(TTFont(NOTO_BOLD_F, _noto_bold_path))
    _noto_available = True

# ── Text helpers ──────────────────────────────────────────────────────────────
def is_latin(ch): return ord(ch) <= 0x00FF

def _jp_font(bold=False, nav_font='droid'):
    """Return the correct JP font name given user's nav_font choice."""
    if nav_font == 'noto' and _noto_available:
        return NOTO_BOLD_F if bold else NOTO_REG
    return JP_FONT

def txt_width(s, size, bold=False, nav_font='droid'):
    return sum(pdfmetrics.stringWidth(ch,
               (LA_BOLD if bold else LA_FONT) if is_latin(ch) else _jp_font(bold, nav_font),
               size) for ch in s)

def draw_text(c, s, x, y, size, color=None, align='left', bold=False, nav_font='droid'):
    if not s: return
    if color: c.setFillColor(color)
    jpf = _jp_font(bold, nav_font)
    if align in ('center', 'right'):
        w = sum(pdfmetrics.stringWidth(ch, (LA_BOLD if bold else LA_FONT) if is_latin(ch) else jpf, size) for ch in s)
        x = (x - w/2) if align == 'center' else (x - w)
    cur_x, run, run_lat = x, '', None
    def flush(seg, lat, cx):
        if not seg: return cx
        f = (LA_BOLD if lat else jpf) if bold else (LA_FONT if lat else jpf)
        c.setFont(f, size); c.drawString(cx, y, seg)
        return cx + pdfmetrics.stringWidth(seg, f, size)
    for ch in s:
        lat = is_latin(ch)
        if run_lat is None: run_lat = lat
        if lat != run_lat: cur_x = flush(run, run_lat, cur_x); run, run_lat = ch, lat
        else: run += ch
    flush(run, run_lat, cur_x)

def draw_bold(c, s, x, y, size, color=None, align='left', nav_font='droid'):
    draw_text(c, s, x, y, size, color, align, bold=True, nav_font=nav_font)

def _draw_rotated_text(c, s, x, y, size):
    if not s: return
    cur_x = x; run, run_lat = '', None
    def flush(seg, lat, cx):
        if not seg: return cx
        f = LA_BOLD if lat else JP_FONT
        c.setFont(f, size); c.drawString(cx, y, seg)
        return cx + pdfmetrics.stringWidth(seg, f, size)
    for ch in s:
        lat = is_latin(ch)
        if run_lat is None: run_lat = lat
        if lat != run_lat: cur_x = flush(run, run_lat, cur_x); run, run_lat = ch, lat
        else: run += ch
    flush(run, run_lat, cur_x)

def truncate_text(s, max_w, size, bold=False, ellipsis='…'):
    if not s or txt_width(s, size, bold) <= max_w: return s
    for i in range(len(s), 0, -1):
        cand = s[:i] + ellipsis
        if txt_width(cand, size, bold) <= max_w: return cand
    return ellipsis

def autosize(s, max_w, max_sz, min_sz=6, bold=False, nav_font='droid'):
    """Return the largest font size ≤ max_sz where text fits in max_w."""
    for sz in range(max_sz, min_sz - 1, -1):
        if txt_width(s, sz, bold, nav_font=nav_font) <= max_w: return sz
    return min_sz

# ── Colour palettes ──────────────────────────────────────────────────────────
PALETTES = {
    'ocean':  {'label':'Ocean',  'primary':'#2b528f','primary_dk':'#1f396d','accent':'#d16946','light':'#f0f3f9','medium':'#dce5f1','secbg':'#e0e9f5','div':'#c5d0e3','steel':'#b4c6e1'},
    'forest': {'label':'Forest', 'primary':'#1c4b2f','primary_dk':'#133721','accent':'#9f561e','light':'#f2fbf5','medium':'#c2f0d2','secbg':'#e0f8e8','div':'#93e2b0','steel':'#5dcb85'},
    'wine':   {'label':'Wine',   'primary':'#79223d','primary_dk':'#57212e','accent':'#ab4b23','light':'#fdf3f3','medium':'#f8d3d8','secbg':'#fce7e9','div':'#f1b0b0','steel':'#e78282'},
    'slate':  {'label':'Slate',  'primary':'#263b57','primary_dk':'#1b2d41','accent':'#17638d','light':'#f2f9fd','medium':'#c2e3f5','secbg':'#e4f1fa','div':'#8dcdec','steel':'#50b4e0'},
    'blush':  {'label':'Blush',  'primary':'#f9e7ed','primary_dk':'#f0c3d2','text_on_primary':'#791d4e','accent':'#9a2759','light':'#fdf2f4','medium':'#f6bccb','secbg':'#f9e7ed','div':'#e79cb5','steel':'#c03366'},
    'mint':   {'label':'Mint',   'primary':'#eaf3ea','primary_dk':'#cce2cd','text_on_primary':'#235627','accent':'#38733b','light':'#f2f7f3','medium':'#abd0ad','secbg':'#eaf3ea','div':'#8abe8c','steel':'#438346'},
    'peach':  {'label':'Peach',  'primary':'#fbf2e4','primary_dk':'#f5debc','text_on_primary':'#a94222','accent':'#cc5733','light':'#fdf8f2','medium':'#efc990','secbg':'#fbf2e4','div':'#e9b363','steel':'#d67c1f'},
    'lilac':  {'label':'Lilac',  'primary':'#ede9f4','primary_dk':'#d2c9e4','text_on_primary':'#4b237d','accent':'#662b8a','light':'#f4f1fc','medium':'#b5a5d3','secbg':'#ede9f4','div':'#9880c2','steel':'#742f92'},
}

# ── Colours ───────────────────────────────────────────────────────────────────
C_NAVY   = colors.HexColor('#2b528f')
C_NAVYDK = colors.HexColor('#1f396d')
C_ACCENT = colors.HexColor('#d16946')
C_WHITE  = colors.white
C_BLACK  = colors.HexColor('#1f2430')
C_MUTED  = colors.HexColor('#5f667b')
C_LBLUE  = colors.HexColor('#f0f3f9')
C_MBLUE  = colors.HexColor('#dce5f1')
C_SECBG  = colors.HexColor('#e0e9f5')
C_DIV    = colors.HexColor('#c5d0e3')
C_STEELBL= colors.HexColor('#b4c6e1')
C_RED    = colors.HexColor('#c53d3d')
C_AMBER  = colors.HexColor('#e9d08a')
C_REDBG  = colors.HexColor('#fdf3f3')
C_REDBDR = colors.HexColor('#e78282')

# ── Drawing primitives ────────────────────────────────────────────────────────
def rect(c, x, y, w, h, fill=None, stroke=None, lw=0.5):
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(lw)
    c.rect(x, y, w, h, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()

def rounded_rect(c, x, y, w, h, fill=None, stroke=None, lw=0.5, r=4):
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()

def styled_rect(c, x, y, w, h, fill=None, stroke=None, lw=0.5,
                corner_style='square', corner_r=6,
                corners=(True, True, True, True)):
    """Rectangle with optional per-corner round or cut (chamfer) treatment.
    corners = (bottom_left, bottom_right, top_left, top_right)
    r is always clamped to min(w,h)/2 so arcs never overflow the element bounds.
    """
    if corner_style == 'square' or corner_r <= 0:
        rect(c, x, y, w, h, fill=fill, stroke=stroke, lw=lw)
        return
    bl, br, tl, tr = corners
    r = min(corner_r, w / 2, h / 2)   # clamp — prevents arc overflow on small elements
    if r <= 0:
        rect(c, x, y, w, h, fill=fill, stroke=stroke, lw=lw)
        return
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(lw)
    p = c.beginPath()
    if corner_style == 'round':
        p.moveTo(x + (r if bl else 0), y)
        p.lineTo(x + w - (r if br else 0), y)
        if br: p.arcTo(x+w-2*r, y,       x+w,   y+2*r,   270, 90)
        p.lineTo(x + w, y + h - (r if tr else 0))
        if tr: p.arcTo(x+w-2*r, y+h-2*r, x+w,   y+h,       0, 90)
        p.lineTo(x + (r if tl else 0), y + h)
        if tl: p.arcTo(x,       y+h-2*r, x+2*r, y+h,      90, 90)
        p.lineTo(x, y + (r if bl else 0))
        if bl: p.arcTo(x,       y,        x+2*r, y+2*r,   180, 90)
    elif corner_style == 'cut':
        p.moveTo(x + (r if bl else 0), y)
        p.lineTo(x + w - (r if br else 0), y)
        if br: p.lineTo(x+w, y+r)
        p.lineTo(x + w, y + h - (r if tr else 0))
        if tr: p.lineTo(x+w-r, y+h)
        p.lineTo(x + (r if tl else 0), y + h)
        if tl: p.lineTo(x, y+h-r)
        p.lineTo(x, y + (r if bl else 0))
        if bl: p.lineTo(x+r, y)
    p.close()
    c.drawPath(p, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()

def vline(c, x, y1, y2, color=C_DIV, lw=0.4):
    c.saveState(); c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x, y1, x, y2); c.restoreState()

def hline(c, x1, x2, y, color=C_DIV, lw=0.4):
    c.saveState(); c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x1, y, x2, y); c.restoreState()

def _photo_clip_path(c, x, y, w, h, cs='square', cr=6):
    """Build a clipping path with rounded or cut corners for photo masking."""
    r = min(cr, w / 2, h / 2)
    p = c.beginPath()
    if cs == 'round' and r > 0:
        p.moveTo(x + r, y)
        p.lineTo(x + w - r, y)
        p.arcTo(x+w-2*r, y,       x+w,   y+2*r,   270, 90)
        p.lineTo(x + w, y + h - r)
        p.arcTo(x+w-2*r, y+h-2*r, x+w,   y+h,       0, 90)
        p.lineTo(x + r, y + h)
        p.arcTo(x,       y+h-2*r, x+2*r, y+h,      90, 90)
        p.lineTo(x, y + r)
        p.arcTo(x,       y,       x+2*r, y+2*r,   180, 90)
    elif cs == 'cut' and r > 0:
        p.moveTo(x + r, y);       p.lineTo(x+w-r, y)
        p.lineTo(x+w, y+r);       p.lineTo(x+w, y+h-r)
        p.lineTo(x+w-r, y+h);     p.lineTo(x+r, y+h)
        p.lineTo(x, y+h-r);       p.lineTo(x, y+r)
    else:
        p.rect(x, y, w, h)
    p.close()
    return p

def photo_placeholder(c, x, y, w, h, label, sublabel='', cs='square', cr=6):
    styled_rect(c, x, y, w, h, fill=colors.HexColor('#ccd5e4'), stroke=None,
                corner_style=cs, corner_r=cr)
    cx = x + w / 2
    draw_text(c, label,    cx, y + h/2 + 6,  12, color=colors.HexColor('#8090a4'), align='center')
    if sublabel:
        draw_text(c, sublabel, cx, y + h/2 - 9, 7.5, color=colors.HexColor('#8090a4'), align='center')

def _orient_image_bytes(raw_bytes):
    """Apply EXIF orientation (handles iPhone portrait shots that arrive
    with an Orientation tag set). Returns oriented bytes; falls back to
    the original on any error or when Pillow is unavailable."""
    if not _PIL_OK or not raw_bytes:
        return raw_bytes
    try:
        with Image.open(io.BytesIO(raw_bytes)) as im:
            ex = im.getexif() if hasattr(im, 'getexif') else None
            orient = ex.get(274) if ex else 1   # 274 = Orientation tag
            if not orient or orient == 1:
                return raw_bytes                # already upright
            fixed = ImageOps.exif_transpose(im)
            fmt = (im.format or 'JPEG').upper()
            if fmt not in ('JPEG', 'PNG'):
                fmt = 'JPEG'
            if fmt == 'JPEG' and fixed.mode in ('RGBA', 'P', 'LA'):
                fixed = fixed.convert('RGB')
            buf = io.BytesIO()
            save_kwargs = {'format': fmt}
            if fmt == 'JPEG':
                save_kwargs['quality'] = 92
            fixed.save(buf, **save_kwargs)
            return buf.getvalue()
    except Exception:
        return raw_bytes

def draw_photo(c, x, y, w, h, b64_data, label, sublabel='', cs='square', cr=6, mode='cover'):
    """Render a base64-encoded image into the (x,y,w,h) rect.

    mode='cover'   → scale the image to FILL the rect, center-crop the
                     overflow via the slot's clip path (default — best
                     for exterior / interior / generic photos).
    mode='contain' → scale the image to FIT inside the rect, letterbox
                     the leftover space (used for floor plans / maps /
                     diagrams where cropping would destroy info).
    """
    if b64_data:
        try:
            raw = b64_data.split(',', 1)[-1] if ',' in b64_data else b64_data
            decoded = _orient_image_bytes(base64.b64decode(raw))
            img = ImageReader(io.BytesIO(decoded))
            iw, ih = img.getSize()
            if not iw or not ih:
                raise ValueError('zero-size image')
            c.saveState()
            cp = _photo_clip_path(c, x, y, w, h, cs, cr)
            c.clipPath(cp, stroke=0)
            if mode == 'cover':
                # Fill the rect; clip path handles overflow.
                scale = max(w / iw, h / ih)
            else:
                # Letterbox inside the rect.
                scale = min(w / iw, h / ih)
            dw, dh = iw * scale, ih * scale
            c.drawImage(img, x + (w-dw)/2, y + (h-dh)/2, dw, dh,
                        preserveAspectRatio=True, mask='auto')
            c.restoreState(); return
        except Exception: pass
    photo_placeholder(c, x, y, w, h, label, sublabel, cs, cr)

def _img_ar(b64_data, default=4/3):
    if b64_data:
        try:
            raw = b64_data.split(',', 1)[-1] if ',' in b64_data else b64_data
            img = ImageReader(io.BytesIO(base64.b64decode(raw)))
            iw, ih = img.getSize()
            return iw / ih if ih else default
        except Exception: pass
    return default

def draw_flex_grid(c, images, x, y, w, h, cs='square', cr=6, modes=None):
    """Aspect-ratio-aware photo grid with white gaps (shadow/mat effect).

    `modes`, if given, is a list aligned 1:1 with `images` containing per-cell
    fit modes ('cover' or 'contain'). Cells without a mode default to 'cover'.
    """
    GAP = 3
    n = len(images)
    if n == 0: return
    ars = [_img_ar(b) for b, _, _ in images]
    def _m(i): return (modes[i] if (modes and i < len(modes) and modes[i]) else 'cover')

    def row(imgs, ars_r, rx, ry, rw, rh, base=0):
        ni = len(imgs); usable = rw - GAP * (ni - 1)
        total = sum(ars_r) or 1; cur_x = rx
        for i, (img_t, ar) in enumerate(zip(imgs, ars_r)):
            cw = usable * ar / total
            if i == ni - 1: cw = rx + rw - cur_x
            draw_photo(c, cur_x, ry, cw, rh, *img_t, cs=cs, cr=cr, mode=_m(base + i))
            cur_x += cw
            if i < ni - 1:
                rect(c, cur_x, ry, GAP, rh, fill=C_WHITE); cur_x += GAP

    if n == 1:
        draw_photo(c, x, y, w, h, *images[0], cs=cs, cr=cr, mode=_m(0))
    elif n == 2:
        row(images, ars, x, y, w, h, base=0)
    elif n == 3:
        rh0 = w / ars[0]; rh1 = w / ((ars[1]+ars[2])/2); tot = rh0+rh1 or 1
        h0 = max(h*.35, min(h*.65, h*rh0/tot)); h1 = h - h0 - GAP
        draw_photo(c, x, y+h1+GAP, w, h0, *images[0], cs=cs, cr=cr, mode=_m(0))
        rect(c, x, y+h1, w, GAP, fill=C_WHITE)
        row(images[1:], ars[1:], x, y, w, h1, base=1)
    else:
        at = (ars[0]+ars[1])/2; ab = (ars[2]+ars[3])/2
        tot = w/at + w/ab or 1
        ht = max(h*.35, min(h*.65, h*(w/at)/tot)); hb = h - ht - GAP
        row(images[:2], ars[:2], x, y+hb+GAP, w, ht)
        rect(c, x, y+hb, w, GAP, fill=C_WHITE)
        row(images[2:], ars[2:], x, y, w, hb)


# ── Generator ─────────────────────────────────────────────────────────────────
def generate(data: dict, out):
    PAGE = landscape(A4)
    c = canvas.Canvas(out, pagesize=PAGE)
    W, H = PAGE                      # ≈ 841.89 × 595.28 pts

    # ── Template dispatch — T1 (default) vs T2 ───────────────────────────────
    if str(data.get('templateId', '1')) == '2':
        _generate_t2(c, W, H, data)
        c.save()
        return

    # ── Style: palette + corner config ────────────────────────────────────────
    _pal = PALETTES.get(data.get('palette', 'ocean'), PALETTES['ocean'])
    # Shadow module-level colours with palette values for this document
    C_NAVY    = colors.HexColor(_pal['primary'])
    C_NAVYDK  = colors.HexColor(_pal['primary_dk'])
    C_ACCENT  = colors.HexColor(_pal['accent'])
    C_LBLUE   = colors.HexColor(_pal['light'])
    C_MBLUE   = colors.HexColor(_pal['medium'])
    C_SECBG   = colors.HexColor(_pal['secbg'])
    C_DIV     = colors.HexColor(_pal['div'])
    C_STEELBL = colors.HexColor(_pal['steel'])
    _light_theme  = 'text_on_primary' in _pal          # palette uses dark-on-light
    C_TEXT_ON_PRI = colors.HexColor(_pal.get('text_on_primary', '#ffffff'))
    # Adaptive footer info text colours (visible on both dark and light footer bg)
    _c_info_main = C_STEELBL if not _light_theme else C_TEXT_ON_PRI
    _c_info_dim  = colors.HexColor('#92a9c4') if not _light_theme else C_TEXT_ON_PRI
    _c_info_dept = colors.HexColor('#afbccf') if not _light_theme else C_TEXT_ON_PRI

    _nav_font = data.get('navFont', 'droid')   # 'droid' | 'noto'
    if _nav_font == 'noto' and not _noto_available:
        _nav_font = 'droid'               # graceful fallback if font not installed

    _cs  = data.get('cornerStyle', 'square')          # 'square' | 'round' | 'cut'
    _cr  = {'small': 4, 'medium': 8, 'large': 14}.get(data.get('cornerSize', 'medium'), 8)
    _csel = data.get('cornerSel', 'all')
    # Corner masks (bl, br, tl, tr) per element
    _MASKS = {
        'all':   {'nav': (True, False, True, False), 'border': (True,  True,  True,  True )},
        'top':   {'nav': (False,False, True, False), 'border': (False, False, True,  True )},
        'outer': {'nav': (False,False, True, False), 'border': (True,  False, False, True )},
        'br':    {'nav': (False,True,  False,False), 'border': (False, True,  False, False)},
    }
    _cm = _MASKS.get(_csel, _MASKS['all'])
    _nav_mask    = _cm['nav']
    _border_mask = _cm['border']
    # Footer bottom corners match the border bottom corners (bl, br only)
    _footer_mask = (_border_mask[0], _border_mask[1], False, False)

    # ── Light-palette contrast helpers ────────────────────────────────────────
    # For light palettes C_NAVY is a pale hue → unusable as text on white.
    # These aliases always resolve to a legible dark colour regardless of palette.
    _c_on_white   = C_TEXT_ON_PRI if _light_theme else C_NAVY
    # Section bar fill / label cell background — use the accent-dark tone for light
    _c_secbar_fill = C_TEXT_ON_PRI if _light_theme else C_NAVY
    _c_seclbl_bg   = C_MBLUE       if _light_theme else C_SECBG  # label cell background
    # Yellow area text: C_NAVYDK is also pale for light palettes
    _c_yell_text   = C_TEXT_ON_PRI if _light_theme else C_NAVYDK

    # ══════════════════════════════════════════════════════════════════════════
    # FIXED GEOMETRY — all constants, computed once.  Nothing resizes at runtime.
    # ══════════════════════════════════════════════════════════════════════════
    MX = 10 * mm
    MY = 7  * mm
    IW = W - 2 * MX                  # usable width  ≈ 821.9 pts

    variant = data.get('templateVariant', 'A').upper()

    # ── Font constants ────────────────────────────────────────────────────────
    PILL_SZ = 10                     # property-type pill text
    ST_FONT = 10                     # station strip (same as pill)

    # ── Horizontal columns ────────────────────────────────────────────────────
    LCW  = IW * 0.34 * 0.85 * 0.85 * 0.85  # left data column  (≈20.8% of IW)
    RW   = IW - LCW
    LX   = MX
    RX   = LX + LCW
    HALF = RW / 2
    RX1  = RX
    RX2  = RX + HALF

    # ── Vertical — footer first, then content above ───────────────────────────
    FOOTER_H = 27.2 * mm             # FIXED footer height (−20% from 34mm)
    FOOTER_Y = MY                    # footer bottom sits at bottom margin

    CTOP      = H - MY               # content top edge
    CBOT      = MY + FOOTER_H + 2*mm # content bottom edge (2mm gap above footer)
    CONTENT_H = CTOP - CBOT

    TOP_H    = CONTENT_H * 0.42      # top photo band height (shorter = tighter navy box)
    BAND_BOT = CTOP - TOP_H          # bottom of top band = top of mid section
    MID_BOT  = CBOT
    MID_TOP  = BAND_BOT
    MID_H    = MID_TOP - MID_BOT

    # ── Left column top-band zones — fixed heights for sections 2+3 ─────────
    PRICE_H = 21 * mm               # price strip  (bottom) — ~6mm gained from nav
    ST_H    = 17 * mm               # station strip (middle) — fits 3 lines
    NAV_H   = TOP_H - PRICE_H - ST_H # nav box      (top) — ~15% shorter

    # Navy box bottom y-coordinate
    nav_y   = BAND_BOT + PRICE_H + ST_H

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT COLUMN — TOP BAND
    # ══════════════════════════════════════════════════════════════════════════

    prop_type = data.get('propertyType', '中古戸建')
    addr_raw  = data.get('address', '')
    short     = addr_raw.replace('東京都','').replace('大阪府','').replace('神奈川県','')[:22]
    prop_name = data.get('propertyName', '').strip()

    # ── Navy box: full TOP_H height, flush to top corner ────────────────────
    # Spans BAND_BOT → CTOP (same boundary as the right-side photos)
    NAV_INNER  = 5
    NAV_GAP    = 4
    pill_pad_x, pill_pad_y = 8, 4

    styled_rect(c, LX, BAND_BOT, LCW, TOP_H, fill=C_NAVY,
                corner_style=_cs, corner_r=_cr, corners=_nav_mask)

    # ── Section 1: NAV_H zone ────────────────────────────────────────────────
    # Elements (name, pill, address) stay tightly together as ONE group.
    # Group is centred in NAV_H with equal space above and below.
    INNER_GAP = 5      # gap between pill and address
    LINE_GAP  = 12     # breathing room for the amber divider line (6pt above + 6pt below)

    pname_sz = autosize(prop_name, LCW - 8, 20, min_sz=7, bold=True, nav_font=_nav_font) if prop_name else 0
    pill_bh  = PILL_SZ + pill_pad_y * 2
    addr_sz  = autosize(short, LCW - 8, 14, min_sz=6, bold=True, nav_font=_nav_font)

    # Group height: name→line uses LINE_GAP, pill→addr uses INNER_GAP
    if prop_name:
        group_h = pname_sz + LINE_GAP + pill_bh + INNER_GAP + addr_sz
    else:
        group_h = pill_bh + INNER_GAP + addr_sz

    # Equal space top and bottom of group inside NAV_H
    side_pad = max(6, (NAV_H - group_h) / 2)

    # cur_y = top of first element's cap (in PDF coords, top of zone minus padding)
    cur_y = (nav_y + NAV_H) - side_pad

    if prop_name:
        cur_y -= pname_sz
        draw_bold(c, prop_name, LX + LCW/2, cur_y, pname_sz,
                  color=C_TEXT_ON_PRI, align='center', nav_font=_nav_font)
        cur_y -= LINE_GAP
        hline(c, LX + 8, LX + LCW - 8, cur_y + LINE_GAP/2, color=C_AMBER, lw=0.8)

    bw     = txt_width(prop_type, PILL_SZ, nav_font=_nav_font) + pill_pad_x * 2
    cur_y -= pill_bh
    pill_x = LX + (LCW - bw) / 2
    rounded_rect(c, pill_x, cur_y, bw, pill_bh, fill=C_ACCENT, r=4)
    draw_text(c, prop_type, pill_x + pill_pad_x, cur_y + pill_pad_y,
              PILL_SZ, color=C_WHITE, nav_font=_nav_font)
    cur_y -= INNER_GAP

    cur_y -= addr_sz
    draw_bold(c, short, LX + LCW/2, cur_y, addr_sz, color=C_TEXT_ON_PRI, align='center',
              nav_font=_nav_font)

    # ── Section 2: Station strip — white bg, dark text, tight spacing ───────
    rect(c, LX, BAND_BOT + PRICE_H, LCW, ST_H, fill=C_WHITE)
    hline(c, LX, LX + LCW, BAND_BOT + PRICE_H + ST_H, color=C_DIV, lw=0.5)
    stations  = data.get('stations', [])[:3]
    ST_PAD    = 3                               # tight top/bottom padding
    n_st      = max(len(stations), 1)
    st_avail  = ST_H - ST_PAD * 2              # drawable height
    # Tighter lines: cap each slice at font + 3pt gap
    st_line_h = min(st_avail / n_st, ST_FONT + 3)
    # Centre the whole block of lines vertically
    block_top = BAND_BOT + PRICE_H + ST_H / 2 + (n_st * st_line_h) / 2
    for i, st in enumerate(stations):
        ln     = st.get('line', '')
        stn    = st.get('station', '').replace('駅', '')
        wk     = st.get('walk', '')
        line_t = truncate_text(f"{ln}　{stn}駅 徒歩{wk}分", LCW - 10, ST_FONT)
        # Baseline centred in each line slice
        st_y   = block_top - (i + 0.5) * st_line_h - ST_FONT * 0.26
        draw_text(c, line_t, LX + LCW/2, st_y, ST_FONT, color=_c_on_white, align='center')

    # ── Section 3: Price strip — white bg, dark label, orange price number ──
    rect(c, LX, BAND_BOT, LCW, PRICE_H, fill=C_WHITE)
    hline(c, LX, LX + LCW, BAND_BOT + PRICE_H, color=C_DIV, lw=0.5)

    price_raw = data.get('price', '')
    num_part  = price_raw.replace('万円', '').strip()
    tax_lbl   = '万円（税込）' if '税込' in data.get('taxIncluded', '税込') else '万円（税別）'
    tax_sz    = ST_FONT
    PRICE_PAD = 7                               # generous top/bottom padding inside strip

    price_sz  = autosize(num_part, LCW - txt_width(tax_lbl, tax_sz, True) - 14,
                         int((PRICE_H - PRICE_PAD * 2) * 0.85), min_sz=9, bold=True)
    combo_w   = txt_width(num_part, price_sz, bold=True) + txt_width(tax_lbl, tax_sz, bold=True) + 4
    price_x   = LX + (LCW - combo_w) / 2
    # Vertically centre price number in padded area
    price_y   = BAND_BOT + PRICE_PAD + ((PRICE_H - PRICE_PAD * 2) - price_sz) / 2
    draw_bold(c, num_part, price_x, price_y, price_sz, color=C_ACCENT)
    draw_text(c, tax_lbl,
              price_x + txt_width(num_part, price_sz, bold=True) + 4,
              price_y + 2, tax_sz, color=C_ACCENT)
    draw_text(c, '販売価格', LX + 5, BAND_BOT + PRICE_H - PRICE_PAD - 1, 5.5, color=_c_on_white)

    rebuild = data.get('rebuild', '')
    if rebuild:
        rbw = txt_width(rebuild, 7) + 10
        rect(c, LX + LCW - rbw - 4, BAND_BOT + PRICE_H - 13, rbw, 11,
             fill=C_REDBG, stroke=C_REDBDR, lw=0.6)
        draw_text(c, rebuild, LX + LCW - rbw/2 - 4, BAND_BOT + PRICE_H - 10, 7,
                  color=C_RED, align='center')

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PHOTO AREA
    # ══════════════════════════════════════════════════════════════════════════
    # White background for entire right photo area; no stroke (grid removed).
    # Drawn FIRST so subsequent photos / flex_grid render on top of it.
    PPAD = 4                            # gap around each photo → 8pt between adjacent photos
    rect(c, RX, MID_BOT, RW, CONTENT_H, fill=C_WHITE)

    if variant == 'B':
        draw_flex_grid(c, [
            (data.get('k1Image',''), '外　観',      '（K1）'),
            (data.get('k2Image',''), '外観写真２',  '（K2）'),
            (data.get('k3Image',''), '外観写真３',  '（K3）'),
            (data.get('k4Image',''), '間取り / 地図','（K4）'),
        ], RX, MID_BOT, RW, CONTENT_H, cs=_cs, cr=_cr,
           modes=[fit_mode('1','B','k1'), fit_mode('1','B','k2'),
                  fit_mode('1','B','k3'), fit_mode('1','B','k4')])

    lease    = data.get('leasePeriod', '')
    grent    = data.get('groundRent', '')
    status   = data.get('currentStatus', '')
    handover = data.get('handover', '')

    if variant != 'B':
        # Q1-top: K1 exterior photo (inset by PPAD for white breathing gap)
        draw_photo(c, RX1 + PPAD, BAND_BOT + PPAD, HALF - PPAD * 2, TOP_H - PPAD * 2,
                   data.get('k1Image',''), '外　観', '（写真をここに挿入）',
                   cs=_cs, cr=_cr, mode=fit_mode('1','A','k1'))
        # Q2-top: K5 map (inset by PPAD)
        draw_photo(c, RX2 + PPAD, BAND_BOT + PPAD, HALF - PPAD * 2, TOP_H - PPAD * 2,
                   data.get('k5Image',''), '地　図', '（地図を挿入）',
                   cs=_cs, cr=_cr, mode=fit_mode('1','A','k5'))

    if variant != 'B':
        k3_img = data.get('k3Image', '').strip()
        if k3_img:
            # Q1-bottom: K3 内観写真 replaces the H/I info box when uploaded
            draw_photo(c, RX1 + PPAD, MID_BOT + PPAD, HALF - PPAD * 2, MID_H - PPAD * 2,
                       k3_img, '内　観', '（内観写真）',
                       cs=_cs, cr=_cr, mode=fit_mode('1','A','k3'))
        else:
            # Q1-bottom: poster-style info panel
            rect(c, RX1, MID_BOT, HALF, MID_H, fill=C_WHITE, stroke=C_DIV, lw=0.5)

            BOX_PAD = 12   # equal margin from all 4 boundaries

            # ── Collect display sections ──────────────────────────────────────
            # Each entry: {'title': str, 'rows': [(left_text, right_text), ...]}
            poster_secs = []
            INNER_W = HALF - BOX_PAD * 2

            nearby = data.get('nearby', [])

            # G — 借地条件 (現況/引渡 already shown in left column — omit here)
            if lease or grent:
                grows = []
                if grent:
                    grows.append((f'地代　{grent}', ''))
                if lease:
                    grows.append((truncate_text(lease, INNER_W * 0.80, 8), ''))
                if grows:
                    poster_secs.append({'title': '借地条件', 'rows': grows})

            # H — 周辺環境
            # walk field may already contain "徒歩約X分" — use as-is to avoid duplication
            nb_rows = [(nb.get('name', ''), nb.get('walk', ''))
                       for nb in nearby if nb.get('name')]
            if nb_rows:
                poster_secs.append({'title': '周辺環境', 'rows': nb_rows})

            # I — 学区
            # dist fields may already contain "徒歩X分" — use as-is
            school_rows = []
            if data.get('elemSchool'):
                school_rows.append((f"小学校：{data['elemSchool']}",
                                    data.get('elemSchoolDist', '')))
            if data.get('juniorSchool'):
                school_rows.append((f"中学校：{data['juniorSchool']}",
                                    data.get('juniorSchoolDist', '')))
            if school_rows:
                poster_secs.append({'title': '学区', 'rows': school_rows})

            # ── Auto-size fonts to fill the space ────────────────────────────
            n_secs = len(poster_secs)
            n_rows = sum(len(s['rows']) for s in poster_secs)

            if n_secs > 0:
                avail_h = MID_H - BOX_PAD * 2
                # Units: each row = 1.0, each title slot = 2.0, inter-sec gap = 0.8
                total_u = n_rows + n_secs * 2.0 + max(0, n_secs - 1) * 0.8
                row_h   = min(avail_h / max(total_u, 1), 26)
                row_h   = max(row_h, 10)

                item_sz  = max(7, min(int(row_h * 0.68), 15))
                title_sz = min(item_sz + 2, 14)
                title_slot = row_h * 2.0      # space reserved per section title (roomier)
                sec_gap    = row_h * 0.8       # gap between sections

                cy = MID_BOT + MID_H - BOX_PAD   # work top-down

                for si, sec in enumerate(poster_secs):
                    # Section title + underline
                    cy -= title_sz + 2
                    draw_bold(c, sec['title'],
                              RX1 + BOX_PAD, cy, title_sz, color=_c_on_white)
                    cy -= 3
                    hline(c, RX1 + BOX_PAD, RX1 + HALF - BOX_PAD, cy + 1.5,
                          color=C_ACCENT if _light_theme else C_STEELBL, lw=0.8)
                    cy -= max(7, title_slot - title_sz - 5)  # generous gap below underline

                    # Rows
                    for (ltext, rtext) in sec['rows']:
                        if ltext:
                            draw_text(c, truncate_text(ltext, INNER_W * 0.74, item_sz),
                                      RX1 + BOX_PAD, cy, item_sz, color=C_BLACK)
                        if rtext:
                            draw_text(c, rtext, RX1 + HALF - BOX_PAD, cy,
                                      item_sz, color=C_MUTED, align='right')
                        cy -= row_h

                    # Gap between sections
                    if si < n_secs - 1:
                        cy -= sec_gap

    # ── Promo banner — upper-right corner, 3 style choices ──────────────────
    promo       = data.get('specialPromo', '').strip()[:8]
    banner_style = data.get('bannerStyle', 'ribbon')   # 'ribbon' | 'stamp' | 'flag'
    if promo:
        cx_r = W - MX    # right edge of content area
        cy_t = CTOP      # top edge
        rsz  = 13.0
        ptw  = txt_width(promo, rsz, bold=True)
        c.saveState()
        # Clip to right photo area only
        cl = c.beginPath(); cl.rect(RX, CBOT, RW, CONTENT_H); c.clipPath(cl, stroke=0)

        if banner_style == 'ribbon':
            # ── Diagonal parallelogram band ──────────────────────────────────
            bw2 = int(rsz * 2.2)
            a   = max(int(ptw / math.sqrt(2)) + bw2 + 16, 80)
            P1  = (cx_r - a,       cy_t)
            P2  = (cx_r - a + bw2, cy_t)
            P3  = (cx_r,           cy_t - a + bw2)
            P4  = (cx_r,           cy_t - a)
            c.setFillColor(colors.HexColor('#00000033'))
            sh = c.beginPath()
            sh.moveTo(P1[0]+3,P1[1]-3); sh.lineTo(P2[0]+3,P2[1]-3)
            sh.lineTo(P3[0]+3,P3[1]-3); sh.lineTo(P4[0]+3,P4[1]-3)
            sh.close(); c.drawPath(sh, fill=1, stroke=0)
            c.setFillColor(C_ACCENT)
            pr = c.beginPath()
            pr.moveTo(*P1); pr.lineTo(*P2); pr.lineTo(*P3); pr.lineTo(*P4)
            pr.close(); c.drawPath(pr, fill=1, stroke=0)
            c.setStrokeColor(C_AMBER); c.setLineWidth(1.0)
            c.line(*P1, *P4); c.line(*P2, *P3)
            mid_x = (P1[0] + P3[0]) / 2
            mid_y = (P1[1] + P3[1]) / 2
            c.translate(mid_x, mid_y); c.rotate(-45)
            c.setFillColor(C_WHITE)
            _draw_rotated_text(c, promo, -ptw / 2, -rsz / 2, rsz)

        elif banner_style == 'stamp':
            # ── Circular stamp in upper-right ────────────────────────────────
            radius  = max(ptw / 2 + 14, rsz + 14)
            margin  = 10
            scx = cx_r - radius - margin
            scy = cy_t - radius - margin
            # Shadow
            c.setFillColor(colors.HexColor('#00000033'))
            c.circle(scx + 3, scy - 3, radius, fill=1, stroke=0)
            # Fill circle
            c.setFillColor(C_ACCENT)
            c.circle(scx, scy, radius, fill=1, stroke=0)
            # Inner dashed ring (stamp effect)
            c.setStrokeColor(C_AMBER); c.setLineWidth(1.2)
            c.setDash([3, 3]); c.circle(scx, scy, radius - 5, fill=0, stroke=1)
            c.setDash([])
            # Text centred, slight tilt
            c.translate(scx, scy); c.rotate(-15)
            c.setFillColor(C_WHITE)
            _draw_rotated_text(c, promo, -ptw / 2, -rsz / 2, rsz)

        elif banner_style == 'flag':
            # ── Vertical flag tab hanging from top-right corner ──────────────
            pad  = 10
            fh   = int(rsz * 2.2) + pad * 2   # total flag height
            fw   = max(int(ptw) + pad * 2, 60) # flag width
            notch = int(fh * 0.38)              # depth of bottom V-notch
            fx   = cx_r - fw                   # left edge of flag
            fy   = cy_t - fh                   # bottom edge (before notch)
            # Shadow
            c.setFillColor(colors.HexColor('#00000033'))
            sh = c.beginPath()
            sh.moveTo(fx+3, cy_t-3); sh.lineTo(cx_r+3, cy_t-3)
            sh.lineTo(cx_r+3, fy-3); sh.lineTo(fx+fw/2+3, fy+notch-3)
            sh.lineTo(fx+3, fy-3); sh.close(); c.drawPath(sh, fill=1, stroke=0)
            # Flag fill
            c.setFillColor(C_ACCENT)
            fl = c.beginPath()
            fl.moveTo(fx, cy_t); fl.lineTo(cx_r, cy_t)
            fl.lineTo(cx_r, fy); fl.lineTo(fx + fw/2, fy + notch)
            fl.lineTo(fx, fy); fl.close()
            c.drawPath(fl, fill=1, stroke=0)
            # Gold border
            c.setStrokeColor(C_AMBER); c.setLineWidth(1.0)
            c.drawPath(fl, fill=0, stroke=1)
            # Text centred horizontally and vertically in flag body
            tx = fx + fw / 2
            ty = fy + (fh - notch - rsz) / 2 + (fh - notch) * 0.05
            draw_bold(c, promo, tx, ty, rsz, color=C_WHITE, align='center')

        c.restoreState()

    # ── Outer content border (styled corners) ────────────────────────────────
    styled_rect(c, MX, CBOT, IW, CONTENT_H,
                fill=None, stroke=C_DIV, lw=0.8,
                corner_style=_cs, corner_r=_cr, corners=_border_mask)

    # ── Single divider: left column | right photo area (no internal photo grid) ─
    vline(c, RX, CBOT, CTOP, color=C_DIV, lw=0.8)

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT COLUMN — MIDDLE SECTION (property data rows)
    # ══════════════════════════════════════════════════════════════════════════
    rect(c, LX, MID_BOT, LCW, MID_H, fill=C_WHITE)

    LLBW = LCW * 0.34
    LVBW = LCW - LLBW

    # ── Pre-build all rows so we can auto-scale row height to fit ─────────────
    # Each entry is either ('sec', title) or ('row', label, value, alt)
    la = f"{data.get('landArea','')}㎡"
    if data.get('landAreaTsubo'): la += f"  ({data['landAreaTsubo']}坪)"
    fa_parts = [data.get(f'floorArea{i}','') for i in range(1,5)]
    fa = '  '.join(x for x in fa_parts if x)
    tf = f"{data.get('totalFloorArea','')}㎡" if data.get('totalFloorArea') else ''

    DISC = '現況と図面が相違する場合は現況を優先します'
    remarks = [r.strip() for r in data.get('remarks','').split('\n')
               if r.strip() and DISC not in r]
    up = []
    if data.get('electric'): up.append(f"電気：{data['electric']}")
    if data.get('gas'):      up.append(f"ガス：{data['gas']}")
    if data.get('water'):    up.append(f"水道：{data['water']}")

    entries = []
    def esec(t):  entries.append(('sec', t))
    def erow(l, v, alt=False):
        if v: entries.append(('row', l, v, alt))

    esec('■ 物件概要')
    erow('土地面積', la)
    erow('土地権利', data.get('landRight',''),     True)
    erow('地目',     data.get('landCategory',''))
    erow('接面道路', data.get('frontRoad',''),      True)
    erow('再建築',   rebuild)
    erow('築年月',   data.get('builtYear',''),      True)
    erow('構造',     data.get('structure',''))
    erow('床面積',   fa,                            True)
    if tf: erow('合計床面積', tf)
    erow('間取り',   data.get('layout',''),         True)
    erow('現況',     status)
    erow('引渡し',   handover,                      True)

    if data.get('propertyType','') == 'マンション':
        esec('■ マンション情報')
        erow('建物名',    data.get('buildingName',''))
        erow('所在階',    data.get('floorInfo',''),    True)
        ea = f"{data.get('exclusiveArea','')}㎡" if data.get('exclusiveArea') else ''
        ba = f"{data.get('balconyArea','')}㎡"  if data.get('balconyArea')   else ''
        erow('専有面積',  ea)
        erow('バルコニー',ba,                          True)
        mf = f"{data.get('managementFee','')}円/月" if data.get('managementFee') else ''
        rf = f"{data.get('repairFund','')}円/月"    if data.get('repairFund')    else ''
        erow('管理費',    mf)
        erow('修繕積立',  rf,                          True)
        erow('管理会社',  data.get('managementCo',''))
        erow('管理形態',  data.get('managementType',''),True)

    if data.get('propertyType','') != 'マンション':
        esec('■ 法令制限')
        erow('都市計画', data.get('cityPlan',''))
        erow('用途地域', data.get('useZone',''),        True)
        erow('防火指定', data.get('fireZone',''))
        erow('建ぺい率', data.get('bcr',''),            True)
        erow('容積率',   data.get('far',''))
        erow('高度地区', data.get('heightDistrict',''), True)
        if data.get('otherLegal'): erow('その他', data['otherLegal'])

    if up:
        esec('■ ライフライン')
        entries.append(('util', '　'.join(up)))

    if remarks:
        esec('■ 備考')
        for i, r in enumerate(remarks):
            erow('', r, bool(i % 2))

    # ── Compute adaptive row height so ALL rows fit in MID_H ──────────────────
    n_sec  = sum(1 for e in entries if e[0] == 'sec')
    n_rows = sum(1 for e in entries if e[0] in ('row', 'util'))
    LBAR_RATIO = 0.92          # section bar ≈ 92% of row height
    # total_h = n_rows * LRH + n_sec * LRH * LBAR_RATIO
    # solve: LRH = MID_H / (n_rows + n_sec * LBAR_RATIO)
    avail   = MID_H - 7        # 7pt reserved for disclaimer at bottom
    if (n_rows + n_sec * LBAR_RATIO) > 0:
        LRH = min(13, avail / (n_rows + n_sec * LBAR_RATIO))
    else:
        LRH = 13
    LRH  = max(LRH, 7)         # never shrink below 7pt (unreadable)
    LBAR = LRH * LBAR_RATIO
    FSZ  = max(5.0, LRH * 0.50)   # label/value font scales with row height

    # ── Draw all collected entries ─────────────────────────────────────────────
    ly = MID_TOP
    for entry in entries:
        if entry[0] == 'sec':
            if ly - LBAR < MID_BOT: break
            ly -= LBAR
            rect(c, LX, ly, LCW, LBAR, fill=_c_secbar_fill)
            draw_bold(c, entry[1], LX+4, ly + LBAR*0.25, FSZ+0.5, color=C_WHITE)

        elif entry[0] == 'row':
            _, lbl, val, alt = entry
            if ly - LRH < MID_BOT: break
            ly -= LRH
            bg = C_LBLUE if alt else C_WHITE
            if lbl:
                # Normal two-cell row: label | value
                rect(c, LX,       ly, LLBW, LRH, fill=_c_seclbl_bg, stroke=C_DIV, lw=0.3)
                draw_text(c, lbl, LX+2, ly + LRH*0.22, FSZ, color=_c_on_white)
                rect(c, LX+LLBW,  ly, LVBW, LRH, fill=bg,     stroke=C_DIV, lw=0.3)
                draw_text(c, truncate_text(val, LVBW-5, FSZ),
                          LX+LLBW+3, ly + LRH*0.22, FSZ, color=C_BLACK)
            else:
                # Full-width merged row (e.g. 備考 lines — no label)
                rect(c, LX, ly, LCW, LRH, fill=bg, stroke=C_DIV, lw=0.3)
                draw_text(c, truncate_text(val, LCW-5, FSZ),
                          LX+3, ly + LRH*0.22, FSZ, color=C_BLACK)

        elif entry[0] == 'util':
            if ly - LRH < MID_BOT: break
            ly -= LRH
            rect(c, LX, ly, LCW, LRH, fill=C_WHITE, stroke=C_DIV, lw=0.3)
            draw_text(c, truncate_text(entry[1], LCW-6, FSZ),
                      LX+3, ly + LRH*0.22, FSZ, color=C_BLACK)

    if MID_BOT + 8 < ly:
        draw_text(c, '※現況と図面が相違する場合は現況を優先します。',
                  LX+2, MID_BOT+4, 5.0, color=C_MUTED)

    # Q2-bottom: K2 floor plan (Variant A) — inset by PPAD
    if variant != 'B':
        draw_photo(c, RX2 + PPAD, MID_BOT + PPAD, HALF - PPAD * 2, MID_H - PPAD * 2,
                   data.get('k2Image',''), '間取り図', '（間取り図を挿入）',
                   cs=_cs, cr=_cr, mode=fit_mode('1','A','k2'))

    # ══════════════════════════════════════════════════════════════════════════
    # FOOTER — FIXED 34mm, IW width, left→right: Logo|Name|Info|Contact|Yellow
    # ══════════════════════════════════════════════════════════════════════════
    F_PAD   = 5
    FY_TOP  = FOOTER_Y + FOOTER_H
    DIVC    = C_TEXT_ON_PRI if _light_theme else colors.HexColor('#364e7e')

    # Fixed section widths (sum = IW)
    F_LOGO_W = FOOTER_H              # square logo
    F_NAME_W = IW * 0.30             # company name — +50% width
    F_INFO_W = IW * 0.18             # address / info — compact
    F_CONT_W = IW * 0.17             # contact (担当者) — just fit
    F_YELL_W = IW - F_LOGO_W - F_NAME_W - F_INFO_W - F_CONT_W  # yellow takes remainder

    # Left-edge x of each section
    F_LOGO_X = MX
    F_NAME_X = F_LOGO_X + F_LOGO_W
    F_INFO_X = F_NAME_X + F_NAME_W
    F_CONT_X = F_INFO_X + F_INFO_W
    F_YELL_X = F_CONT_X + F_CONT_W

    # Navy background (full IW width) — styled bottom corners
    styled_rect(c, MX, FOOTER_Y, IW, FOOTER_H, fill=C_NAVYDK,
                corner_style=_cs, corner_r=_cr, corners=_footer_mask)

    # ── a) Logo (leftmost square) ─────────────────────────────────────────────
    logo_b64 = data.get('logoImage', '')
    if logo_b64:
        try:
            raw = logo_b64.split(',',1)[-1] if ',' in logo_b64 else logo_b64
            li  = ImageReader(io.BytesIO(base64.b64decode(raw)))
            lw2, lh2 = li.getSize()
            sc = min(F_LOGO_W/lw2, FOOTER_H/lh2) * 0.88 if lw2 and lh2 else 1
            dw, dh = lw2*sc, lh2*sc
            c.drawImage(li, F_LOGO_X+(F_LOGO_W-dw)/2, FOOTER_Y+(FOOTER_H-dh)/2,
                        dw, dh, preserveAspectRatio=True, mask='auto')
        except Exception: pass

    # (no vline dividers inside footer — clean solid band)

    # ── b) Company name — vertically centred in footer ───────────────────────
    brand = data.get('brandName', '')
    co    = data.get('companyName', '')
    av_nw    = F_NAME_W - F_PAD * 2
    brand_sz = autosize(brand, av_nw, 22, min_sz=7, bold=True) if brand else 0
    co_sz    = autosize(co,    av_nw, 18, min_sz=7, bold=True) if (co and co != brand) else 0
    N_GAP = 4
    have_b = bool(brand); have_c = bool(co and co != brand)
    # True visual centering: ReportLab baseline ≠ visual midpoint
    # Text ascends ~0.72×sz above baseline, descends ~0.20×sz below.
    # Formula: ny = center + (block_h - 0.72*first_sz - 0.80*last_sz) / 2
    fc_y = FOOTER_Y + FOOTER_H / 2          # footer visual centre
    if have_b and have_c:
        block_h = brand_sz + N_GAP + co_sz
        ny = fc_y + (block_h - 0.72 * brand_sz - 0.80 * co_sz) / 2
    elif have_b:
        ny = fc_y - 0.26 * brand_sz         # single line: baseline below centre
    elif have_c:
        ny = fc_y - 0.26 * co_sz
    else:
        ny = fc_y
    # Left-align: anchor text at left edge of section plus padding
    name_lx = F_NAME_X + F_PAD
    if have_b:
        draw_bold(c, brand, name_lx, ny, brand_sz, color=C_TEXT_ON_PRI)
        ny -= brand_sz + N_GAP
    if have_c:
        draw_bold(c, co, name_lx, ny, co_sz, color=C_TEXT_ON_PRI)


    # ── c) Company info — vertically centred ─────────────────────────────────
    ISZ       = 7.0
    IGAP      = 2.5
    addr_co   = data.get('companyAddress', '')
    tel       = data.get('tel', '')
    fax       = data.get('fax', '')
    em        = data.get('email', '')
    dept      = data.get('department', '')
    licenseNo = data.get('licenseNo', '')
    assoc     = data.get('association', '')
    # Build rows as (text, colour, size) — collect first, draw after centering
    info_rows = []
    if dept:      info_rows.append((dept,    _c_info_dept, ISZ))
    if addr_co:   info_rows.append((addr_co, _c_info_main, ISZ))
    if tel and fax:
        info_rows.append((f'TEL：{tel}  FAX：{fax}', _c_info_main, ISZ))
    elif tel:     info_rows.append((f'TEL：{tel}',   _c_info_main, ISZ))
    elif fax:     info_rows.append((f'FAX：{fax}',   _c_info_main, ISZ))
    if em:        info_rows.append((f'✉ {em}',        _c_info_main, ISZ))
    if licenseNo: info_rows.append((licenseNo, _c_info_dim,  ISZ-1))
    if assoc:     info_rows.append((assoc,     _c_info_dim,  ISZ-1.5))
    # Total block height → centre in footer
    if info_rows:
        total_h = sum(sz for _, _, sz in info_rows) + IGAP * (len(info_rows) - 1)
        iy = FOOTER_Y + FOOTER_H / 2 + total_h / 2   # top baseline of first row
        for txt, col, sz in info_rows:
            draw_text(c, truncate_text(txt, F_INFO_W - F_PAD * 2, sz),
                      F_INFO_X + F_PAD, iy, sz, color=col)
            iy -= sz + IGAP

    # ── d) Contact ────────────────────────────────────────────────────────────
    OBC_H        = int(FOOTER_H * 0.16)          # strip height ≈16% of footer
    strip_w      = F_CONT_W * 0.60               # 40% narrower (floats)
    strip_margin = (F_CONT_W - strip_w) / 2
    strip_x      = F_CONT_X + strip_margin
    strip_y      = FY_TOP - OBC_H * 1.5          # lowered by half strip height

    rounded_rect(c, strip_x, strip_y, strip_w, OBC_H, fill=C_ACCENT, r=3)
    draw_bold(c, 'お問い合わせ先',
              strip_x + strip_w/2, strip_y + 3, 9, color=C_WHITE, align='center')

    ag      = data.get('agentName', '')
    ag_tel  = data.get('agentTel', '')
    tel_str = ag_tel or tel
    CW      = F_CONT_W - F_PAD * 2

    # Compute text sizes before positioning
    asz = autosize(f'【担当】{ag}', CW, 14, min_sz=7, bold=True) if ag else 0
    tsz = autosize(f'TEL：{tel_str}', CW, 15, min_sz=7, bold=True) if tel_str else 0
    ROW_GAP = 3
    have_ag  = bool(ag); have_tel = bool(tel_str)
    if have_ag and have_tel:   block_h = asz + ROW_GAP + tsz
    elif have_ag:              block_h = asz
    elif have_tel:             block_h = tsz
    else:                      block_h = 0

    # Vertically centre agent/tel in the space BELOW the orange strip
    sub_center = FOOTER_Y + (strip_y - FOOTER_Y) / 2   # mid of sub-strip space
    if have_ag and have_tel:
        cy2 = sub_center + (block_h - 0.72 * asz - 0.80 * tsz) / 2
    elif have_ag:
        cy2 = sub_center - 0.26 * asz
    elif have_tel:
        cy2 = sub_center - 0.26 * tsz
    else:
        cy2 = sub_center

    if have_ag:
        draw_bold(c, f'【担当】{ag}', F_CONT_X+F_PAD, cy2, asz, color=C_TEXT_ON_PRI)
        cy2 -= asz + ROW_GAP
    if have_tel:
        draw_bold(c, f'TEL：{tel_str}', F_CONT_X+F_PAD, cy2, tsz, color=C_TEXT_ON_PRI)

    # ── e) Yellow slogan area (rightmost) ─────────────────────────────────────
    # Right corner of footer matches border_mask tr corner
    _yell_mask = (False, _border_mask[1], False, False)
    styled_rect(c, F_YELL_X, FOOTER_Y, F_YELL_W, FOOTER_H,
                fill=colors.HexColor('#d6b51f'),
                corner_style=_cs, corner_r=_cr, corners=_yell_mask)

    slogan = data.get('catchcopy', data.get('companySlogan', ''))
    ttype  = data.get('transactionType', '')
    fee    = data.get('fee', '')
    YPW    = F_YELL_W - F_PAD*2

    # Slogan in top ~65% of yellow area — try 2-line wrap for larger display
    yell_top_zone = FOOTER_H * 0.65
    if slogan:
        # Single-line size
        ssz_1 = autosize(slogan, YPW, int(yell_top_zone * 0.82), min_sz=6, bold=True)
        slogan_lines = [slogan]
        best_ssz = ssz_1

        # Try 2-line splits near midpoint; pick the split yielding the largest font
        if len(slogan) >= 6:
            mid = len(slogan) // 2
            max2 = int(yell_top_zone / 2.4)   # max per-line size when 2 lines fit
            for sp in range(max(2, mid - 4), min(len(slogan) - 1, mid + 5)):
                l1, l2 = slogan[:sp], slogan[sp:]
                longer = l1 if txt_width(l1, 1, bold=True) >= txt_width(l2, 1, bold=True) else l2
                sz2 = autosize(longer, YPW, max2, min_sz=6, bold=True)
                if sz2 > best_ssz:
                    best_ssz = sz2
                    slogan_lines = [l1, l2]

        line_gap = max(2, best_ssz // 6)
        sy = FY_TOP - F_PAD - best_ssz          # top-line baseline
        for line in slogan_lines:
            draw_bold(c, line, F_YELL_X + F_PAD, sy, best_ssz, color=_c_yell_text)
            sy -= best_ssz + line_gap

    # 取引態様 / 手数料 — fixed ISZ size (matches company info column),
    # centred horizontally and vertically in the bottom ~35% zone of yellow area.
    BSZ       = ISZ                              # same size as company info text
    bot_zone_h = FOOTER_H * 0.35                # bottom zone height
    bot_parts = list(filter(None, [
        f'【取引態様】{ttype}' if ttype else '',
        f'【手数料】{fee}'     if fee   else '',
    ]))
    if bot_parts:
        bot_line = '　　'.join(bot_parts)
        # Vertically: centre in the bottom zone, minimum F_PAD above footer edge
        bot_ctr_y = FOOTER_Y + bot_zone_h / 2   # centre of bottom zone
        bot_y     = max(bot_ctr_y, FOOTER_Y + F_PAD + BSZ * 0.2)
        # Horizontally: centre in yellow area
        bw_txt = txt_width(bot_line, BSZ, bold=True)
        bot_x  = F_YELL_X + (F_YELL_W - bw_txt) / 2
        draw_bold(c, bot_line, bot_x, bot_y, BSZ, color=_c_yell_text)

    c.save()


# ══════════════════════════════════════════════════════════════════════════════
# TEMPLATE 2 — 株式会社成宏商事 sample style  (sub-variants 2A and 2B)
# ══════════════════════════════════════════════════════════════════════════════
def _draw_starburst(c, cx, cy, r_outer, r_inner, n_points=12,
                    fill=None, stroke=None, lw=0.6, rot=0.0):
    """Filled n-pointed starburst centred at (cx, cy)."""
    p = c.beginPath()
    for i in range(n_points * 2):
        ang = math.pi * i / n_points - math.pi / 2 + rot
        r = r_outer if i % 2 == 0 else r_inner
        x = cx + r * math.cos(ang)
        y = cy + r * math.sin(ang)
        if i == 0: p.moveTo(x, y)
        else:      p.lineTo(x, y)
    p.close()
    c.saveState()
    if fill is not None:   c.setFillColor(fill)
    if stroke is not None: c.setStrokeColor(stroke); c.setLineWidth(lw)
    c.drawPath(p, fill=1 if fill is not None else 0,
                  stroke=1 if stroke is not None else 0)
    c.restoreState()


def _generate_t2(c, W, H, data: dict):
    """Template 2 — sample-accurate flyer (株式会社成宏商事 reference style).

    Layout: white header (title / price / transit) — green+cream double-line
    frame around photo collage + plain detail rows — single disclaimer line —
    simple white footer (company name + info columns + ■取引態様 ■手数料 markers).

    Sub-variants:
      2A — 4-line transit list in a cream tile + yellow N線 starburst,
           K3 circular building-emblem overlay on K1, K4 map tile,
           BLUE price colour. (e.g. 日神パレス新三河島 sample)
      2B — Single green double-stroked station tag, optional yellow
           yield-callout ellipse on K1, GREEN price colour.
           (e.g. バロンハイツ大塚 sample)
    """
    # ── Fixed sample palette (does not vary with `palette` form field) ──────
    C_GREEN_DK   = colors.HexColor('#287c40')   # frame outer / 2B price / labels
    C_GREEN_LT   = colors.HexColor('#45975e')
    C_CREAM_LT   = colors.HexColor('#faf4e6')   # transit tile fill
    C_CREAM_BD   = colors.HexColor('#dcc595')   # frame inner stripe / row hairline
    C_RED_DK     = colors.HexColor('#b1273d')   # 売 pill / 稀有 burst
    C_YELLOW     = colors.HexColor('#dfc320')   # N線 burst / 新 badge
    C_YELLOW_DK  = colors.HexColor('#af8b19')
    C_BLUE_PRICE = colors.HexColor('#2f6397')   # 2A price colour
    C_BROWN_TXT  = colors.HexColor('#352915')   # text on cream
    C_GREY_TXT   = colors.HexColor('#5a5a5a')
    C_TINT_BEIGE = colors.HexColor('#f7f1e2')   # alt-row tint

    _nav_font = data.get('navFont', 'droid')
    if _nav_font == 'noto' and not _noto_available:
        _nav_font = 'droid'

    _cs   = data.get('cornerStyle', 'square')
    _cr   = {'small': 4, 'medium': 8, 'large': 14}.get(data.get('cornerSize', 'medium'), 8)
    _csel = data.get('cornerSel', 'all')
    _MASKS = {
        'all':   (True,  True,  True,  True ),
        'top':   (False, False, True,  True ),
        'outer': (True,  False, False, True ),
        'br':    (False, True,  False, False),
    }
    _border_mask = _MASKS.get(_csel, _MASKS['all'])

    variant = (data.get('templateVariant', 'A') or 'A').upper()
    price_color = C_BLUE_PRICE if variant == 'A' else C_GREEN_DK

    # ── Geometry ──────────────────────────────────────────────────────────────
    MX = 10 * mm
    MY = 7  * mm
    IW = W - 2 * MX

    HEADER_H = 28 * mm
    FOOTER_H = 22 * mm
    DISC_H   = 5  * mm

    HEADER_TOP = H - MY
    HEADER_BOT = HEADER_TOP - HEADER_H
    FOOTER_BOT = MY
    FOOTER_TOP = MY + FOOTER_H
    DISC_BOT   = FOOTER_TOP
    DISC_TOP   = DISC_BOT + DISC_H
    FRAME_TOP  = HEADER_BOT
    FRAME_BOT  = DISC_TOP
    FRAME_H    = FRAME_TOP - FRAME_BOT

    # ══════════════════════════════════════════════════════════════════════
    # HEADER STRIP  (white bg, 3 zones: title | price | transit)
    # ══════════════════════════════════════════════════════════════════════
    HD_PAD     = 4
    HD_TITLE_W = IW * 0.36
    HD_PRICE_W = IW * 0.34
    HD_TRANS_W = IW - HD_TITLE_W - HD_PRICE_W
    HD_TITLE_X = MX
    HD_PRICE_X = MX + HD_TITLE_W
    HD_TRANS_X = HD_PRICE_X + HD_PRICE_W
    HD_LX      = HD_TITLE_X + HD_PAD

    prop_type = (data.get('propertyType', '') or '').strip()
    prop_name = (data.get('propertyName', '') or '').strip()
    prop_hl   = (data.get('propertyHighlight', '') or '').strip()

    # ── (1) Title zone — LEFT ───────────────────────────────────────────────
    title_avail_w = HD_TITLE_W - HD_PAD * 2
    pill_sz       = 9
    pill_pad_x, pill_pad_y = 7, 3
    pill_h        = pill_sz + pill_pad_y * 2
    pill_top_y    = HEADER_TOP - 6
    pill_y        = pill_top_y - pill_h
    if prop_type:
        bw = txt_width(prop_type, pill_sz, bold=True, nav_font=_nav_font) + pill_pad_x * 2
        rounded_rect(c, HD_LX, pill_y, bw, pill_h, fill=C_RED_DK, r=2)
        draw_bold(c, prop_type, HD_LX + pill_pad_x, pill_y + pill_pad_y,
                  pill_sz, color=C_WHITE, nav_font=_nav_font)
        name_top = pill_y - 2
    else:
        name_top = HEADER_TOP - 4

    name_sz = autosize(prop_name, title_avail_w, 24, min_sz=10,
                       bold=True, nav_font=_nav_font) if prop_name else 0
    name_y  = max(HEADER_BOT + 12, name_top - name_sz)
    if prop_name:
        draw_bold(c, prop_name, HD_LX, name_y, name_sz,
                  color=C_BLACK, nav_font=_nav_font)

    if prop_hl:
        hl_sz = autosize(prop_hl, title_avail_w, 10, min_sz=7, nav_font=_nav_font)
        hl_y  = max(HEADER_BOT + 3, name_y - hl_sz - 4)
        draw_text(c, prop_hl, HD_LX, hl_y, hl_sz,
                  color=C_GREY_TXT, nav_font=_nav_font)

    # ── (2) Price zone — CENTRE ────────────────────────────────────────────
    price_num     = (data.get('priceNum', '') or '').strip()
    price_tax     = (data.get('priceTax', '税込み') or '税込み').strip()
    price_inner_x = HD_PRICE_X + HD_PAD
    price_inner_w = HD_PRICE_W - HD_PAD * 2

    # 稀有 starburst (top-left of price zone)
    rare_inset = 0
    if data.get('rareBadgeOn'):
        rare_text = (data.get('rareBadgeText', '稀有') or '稀有').strip() or '稀有'
        sb_r  = 13
        sb_cx = price_inner_x + sb_r + 1
        sb_cy = HEADER_TOP - sb_r - 4
        _draw_starburst(c, sb_cx, sb_cy, r_outer=sb_r, r_inner=sb_r * 0.55,
                        n_points=12, fill=C_RED_DK)
        rb_chars = len(rare_text)
        rb_sz = 9 if rb_chars <= 2 else (7 if rb_chars <= 3 else 6)
        if rb_chars >= 4:
            half = rb_chars // 2
            l1, l2 = rare_text[:half], rare_text[half:]
            draw_bold(c, l1, sb_cx, sb_cy + 1, rb_sz,
                      color=C_WHITE, align='center', nav_font=_nav_font)
            draw_bold(c, l2, sb_cx, sb_cy - rb_sz - 1, rb_sz,
                      color=C_WHITE, align='center', nav_font=_nav_font)
        else:
            draw_bold(c, rare_text, sb_cx, sb_cy - rb_sz * 0.32, rb_sz,
                      color=C_WHITE, align='center', nav_font=_nav_font)
        rare_inset = sb_r * 2 + 4

    # 新 yellow badge (top-right of price zone) — optional
    new_inset = 0
    if data.get('newPriceBadge'):
        nb_sz = 13
        nb_w  = txt_width('新', nb_sz, bold=True, nav_font=_nav_font) + 12
        nb_h  = nb_sz + 8
        nb_x  = HD_PRICE_X + HD_PRICE_W - HD_PAD - nb_w
        nb_y  = HEADER_TOP - 6 - nb_h
        rounded_rect(c, nb_x, nb_y, nb_w, nb_h, fill=C_YELLOW,
                     stroke=C_RED_DK, lw=0.8, r=3)
        draw_bold(c, '新', nb_x + nb_w/2, nb_y + 4, nb_sz,
                  color=C_RED_DK, align='center', nav_font=_nav_font)
        new_inset = nb_w + 4

    # 価格 + number + 万円 — auto-fit
    pblk_x = price_inner_x + rare_inset
    pblk_w = price_inner_w - rare_inset - new_inset
    if price_num:
        pn_sz, pl_sz, yen_sz = 14, 9, 9
        for cand in range(40, 14, -1):
            psz_lbl = max(10, int(cand * 0.42))
            psz_yen = max(11, int(cand * 0.46))
            w_test = (txt_width('価格', psz_lbl, bold=True, nav_font=_nav_font) + 4 +
                      txt_width(price_num, cand, bold=True, nav_font=_nav_font) + 1 +
                      txt_width('万円', psz_yen, bold=True, nav_font=_nav_font))
            if w_test <= pblk_w:
                pn_sz, pl_sz, yen_sz = cand, psz_lbl, psz_yen
                break
        price_y = HEADER_BOT + (HEADER_H - pn_sz) / 2 + 2
        # 価格 (small label)
        draw_bold(c, '価格', pblk_x, price_y + (pn_sz - pl_sz) * 0.55,
                  pl_sz, color=price_color, nav_font=_nav_font)
        cur_x = pblk_x + txt_width('価格', pl_sz, bold=True, nav_font=_nav_font) + 4
        # number (huge)
        draw_bold(c, price_num, cur_x, price_y, pn_sz,
                  color=price_color, nav_font=_nav_font)
        cur_x += txt_width(price_num, pn_sz, bold=True, nav_font=_nav_font) + 1
        # 万円
        draw_bold(c, '万円', cur_x, price_y + (pn_sz - yen_sz) * 0.5,
                  yen_sz, color=price_color, nav_font=_nav_font)
        # （税込み）below price
        if price_tax:
            tax_sz = 9
            tax_y  = price_y - tax_sz - 2
            if tax_y > HEADER_BOT + 2:
                draw_text(c, f'（{price_tax}）', pblk_x, tax_y, tax_sz,
                          color=C_GREY_TXT, nav_font=_nav_font)

    # ── (3) Transit zone — RIGHT ───────────────────────────────────────────
    layout_type = (data.get('layoutType', '') or '').strip()
    stations    = data.get('stations', []) or []
    tr_inner_x  = HD_TRANS_X + HD_PAD
    tr_avail_w  = HD_TRANS_W - HD_PAD * 2

    # 2DK / 3LDK at top-left of transit zone
    if layout_type:
        lt_sz = autosize(layout_type, tr_avail_w * 0.55, 26, min_sz=12,
                         bold=True, nav_font=_nav_font)
        lt_y  = HEADER_TOP - 6 - lt_sz
        draw_bold(c, layout_type, tr_inner_x, lt_y, lt_sz,
                  color=C_BLACK, nav_font=_nav_font)
    else:
        lt_sz = 0
        lt_y  = HEADER_TOP - 6

    if variant == 'B' and stations:
        st  = stations[0]
        ln  = (st.get('line', '') or '').strip()
        stn = (st.get('station', '') or '').replace('駅', '').strip()
        wk  = (st.get('walk', '') or '').strip()
        if ln:
            draw_bold(c, ln, tr_inner_x, lt_y - 13, 9.5,
                      color=C_GREEN_DK, nav_font=_nav_font)
            tag_top = lt_y - 16
        else:
            tag_top = lt_y - 4
        tag_text = f'{stn}駅 徒歩{wk}分' if (stn and wk) else (f'{stn}駅' if stn else '')
        if tag_text:
            tag_sz = autosize(tag_text, tr_avail_w - 12, 13, min_sz=8,
                              bold=True, nav_font=_nav_font)
            tw = txt_width(tag_text, tag_sz, bold=True, nav_font=_nav_font) + 14
            th = tag_sz + 8
            ty = max(tag_top - th, HEADER_BOT + 3)
            tx = tr_inner_x
            c.saveState()
            c.setFillColor(C_GREEN_DK); c.setStrokeColor(C_GREEN_DK); c.setLineWidth(0.4)
            c.roundRect(tx, ty, tw, th, th/2, fill=1, stroke=1)
            c.setStrokeColor(C_WHITE); c.setLineWidth(0.8)
            c.roundRect(tx + 1.6, ty + 1.6, tw - 3.2, th - 3.2,
                        max(1, (th - 3.2)/2), fill=0, stroke=1)
            c.restoreState()
            draw_bold(c, tag_text, tx + tw/2, ty + 4, tag_sz,
                      color=C_WHITE, align='center', nav_font=_nav_font)
    elif variant == 'A':
        lines = stations[:4]
        n = len(lines)
        if n > 0:
            cream_top = lt_y - 4
            cream_bot = HEADER_BOT + 3
            cream_h   = max(cream_top - cream_bot, 18)
            cream_top = cream_bot + cream_h
            rounded_rect(c, tr_inner_x, cream_bot, tr_avail_w, cream_h,
                         fill=C_CREAM_LT, stroke=C_CREAM_BD, lw=0.8, r=2)
            # Yellow N線 burst — corner sticker, anchored inside the cream
            # tile.  First transit line is indented past it so they don't
            # collide.
            burst_r = 10
            burst_cx = tr_inner_x + burst_r + 1
            burst_cy = cream_top - burst_r - 1
            burst_text = f'{n}線'
            _draw_starburst(c, burst_cx, burst_cy,
                            r_outer=burst_r, r_inner=burst_r * 0.55,
                            n_points=10, fill=C_YELLOW,
                            stroke=C_YELLOW_DK, lw=0.6)
            burst_sz = 8 if len(burst_text) <= 2 else 6
            draw_bold(c, burst_text, burst_cx, burst_cy - burst_sz * 0.34,
                      burst_sz, color=C_RED_DK, align='center',
                      nav_font=_nav_font)
            slot_h  = (cream_h - 4) / max(n, 1)
            line_sz = max(7, min(int(slot_h * 0.52), 9))
            burst_right = burst_cx + burst_r + 4
            for i, t in enumerate(lines):
                ln  = (t.get('line', '') or '').strip()
                stn = (t.get('station', '') or '').replace('駅', '').strip()
                wk  = (t.get('walk', '') or '').strip()
                txt = f'■ {ln}　{stn}駅 徒歩{wk}分' if (ln or stn) else ''
                if not txt: continue
                ly = cream_top - 3 - (i + 0.7) * slot_h
                # Indent the FIRST line past the corner burst so they
                # don't collide.
                lx     = (burst_right if i == 0 else tr_inner_x + 6)
                avail  = tr_avail_w - (lx - tr_inner_x) - 8
                draw_text(c, truncate_text(txt, avail, line_sz),
                          lx, ly, line_sz,
                          color=C_BROWN_TXT, nav_font=_nav_font)

    # ══════════════════════════════════════════════════════════════════════
    # FRAME — green outer + cream inner double-line border
    # ══════════════════════════════════════════════════════════════════════
    styled_rect(c, MX, FRAME_BOT, IW, FRAME_H, fill=None,
                stroke=C_GREEN_DK, lw=2.6,
                corner_style=_cs, corner_r=_cr, corners=_border_mask)
    INSET = 1.6 * mm
    styled_rect(c, MX + INSET, FRAME_BOT + INSET,
                IW - INSET*2, FRAME_H - INSET*2,
                fill=None, stroke=C_CREAM_BD, lw=1.0,
                corner_style=_cs, corner_r=max(1, _cr - 2),
                corners=_border_mask)

    INNER_PAD = INSET + 1.4 * mm
    IN_X = MX + INNER_PAD
    IN_Y = FRAME_BOT + INNER_PAD
    IN_W = IW - INNER_PAD * 2
    IN_H = FRAME_H - INNER_PAD * 2

    SPLIT_GAP = 3 * mm
    PHOTO_W   = IN_W * 0.62 - SPLIT_GAP / 2
    DETAIL_W  = IN_W * 0.38 - SPLIT_GAP / 2
    PHOTO_X   = IN_X
    DETAIL_X  = IN_X + PHOTO_W + SPLIT_GAP

    # ══════════════════════════════════════════════════════════════════════
    # PHOTO AREA  (left of frame) — variant-specific
    # ══════════════════════════════════════════════════════════════════════
    PG = 3
    if variant == 'A':
        # 2A: K1 main + K4 map (top), K2 floor plan (mid), K5/6/7 thumbs (bot)
        TOP_H = PHOTO_W * 0.42
        BOT_H = PHOTO_W * 0.18
        MID_H = IN_H - TOP_H - BOT_H - PG * 2
        if MID_H < 30:
            TOP_H = (IN_H - BOT_H - PG * 2) * 0.6
            MID_H = IN_H - TOP_H - BOT_H - PG * 2
        K1_W = PHOTO_W * 0.62
        K4_W = PHOTO_W - K1_W - PG
        K1_X = PHOTO_X
        K1_Y = IN_Y + IN_H - TOP_H
        draw_photo(c, K1_X, K1_Y, K1_W, TOP_H,
                   data.get('k1Image', ''), '外観メイン', '（K1）',
                   cs=_cs, cr=_cr, mode=fit_mode('2','A','k1'))
        K4_X = K1_X + K1_W + PG
        draw_photo(c, K4_X, K1_Y, K4_W, TOP_H,
                   data.get('k4Image', ''), '地図', '（K4）',
                   cs=_cs, cr=_cr, mode=fit_mode('2','A','k4'))
        K2_X = PHOTO_X
        K2_Y = K1_Y - PG - MID_H
        draw_photo(c, K2_X, K2_Y, PHOTO_W, MID_H,
                   data.get('k2Image', ''), '間取り図', '（K2）',
                   cs=_cs, cr=_cr, mode=fit_mode('2','A','k2'))
        TH_KEYS   = ['k5Image', 'k6Image', 'k7Image']
        TH_LABELS = [('内観1', 'K5'), ('内観2', 'K6'), ('内観3', 'K7')]
        TH_N = len(TH_KEYS)
        TW = (PHOTO_W - PG * (TH_N - 1)) / TH_N
        TY = IN_Y
        for i, (key, (lab, sub)) in enumerate(zip(TH_KEYS, TH_LABELS)):
            tx = PHOTO_X + i * (TW + PG)
            slot = key.replace('Image', '').lower()  # 'k5'/'k6'/'k7'
            draw_photo(c, tx, TY, TW, BOT_H,
                       data.get(key, ''), lab, f'（{sub}）',
                       cs=_cs, cr=_cr, mode=fit_mode('2','A',slot))
        # K3 — circular building-emblem overlay (top-right of K1)
        k3_b64 = data.get('k3Image', '')
        if k3_b64:
            ov_r  = min(K1_W, TOP_H) * 0.16
            ov_cx = K1_X + K1_W - ov_r - 6
            ov_cy = K1_Y + TOP_H - ov_r - 6
            c.saveState()
            c.setFillColor(C_CREAM_LT)
            c.circle(ov_cx, ov_cy, ov_r + 2.5, fill=1, stroke=0)
            c.restoreState()
            c.saveState()
            cp = c.beginPath(); cp.circle(ov_cx, ov_cy, ov_r); c.clipPath(cp, stroke=0)
            try:
                raw = k3_b64.split(',', 1)[-1] if ',' in k3_b64 else k3_b64
                decoded = _orient_image_bytes(base64.b64decode(raw))
                img = ImageReader(io.BytesIO(decoded))
                iw, ih = img.getSize()
                box   = ov_r * 2
                scale = max(box / iw, box / ih) if iw and ih else 1
                dw, dh = iw * scale, ih * scale
                c.drawImage(img, ov_cx - dw/2, ov_cy - dh/2, dw, dh,
                            preserveAspectRatio=True, mask='auto')
            except Exception: pass
            c.restoreState()
            c.saveState()
            c.setStrokeColor(C_GREEN_DK); c.setLineWidth(1.4)
            c.circle(ov_cx, ov_cy, ov_r, fill=0, stroke=1)
            c.restoreState()
    else:
        # 2B: K1 + K2 (top), K3-K7 (bottom); optional yellow yield-callout on K1
        TOP_H = IN_H * 0.58
        BOT_H = IN_H - TOP_H - PG
        K1_W  = PHOTO_W * 0.62
        K2_W  = PHOTO_W - K1_W - PG
        K1_X  = PHOTO_X
        K1_Y  = IN_Y + BOT_H + PG
        draw_photo(c, K1_X, K1_Y, K1_W, TOP_H,
                   data.get('k1Image', ''), '外観メイン', '（K1）',
                   cs=_cs, cr=_cr, mode=fit_mode('2','B','k1'))
        K2_X = K1_X + K1_W + PG
        draw_photo(c, K2_X, K1_Y, K2_W, TOP_H,
                   data.get('k2Image', ''), '間取り図', '（K2）',
                   cs=_cs, cr=_cr, mode=fit_mode('2','B','k2'))
        TH_KEYS   = ['k3Image', 'k4Image', 'k5Image', 'k6Image', 'k7Image']
        TH_LABELS = [('外観', 'K3'), ('共用部', 'K4'),
                     ('内観1', 'K5'), ('内観2', 'K6'), ('内観3', 'K7')]
        TH_N = len(TH_KEYS)
        TW = (PHOTO_W - PG * (TH_N - 1)) / TH_N
        TY = IN_Y
        for i, (key, (lab, sub)) in enumerate(zip(TH_KEYS, TH_LABELS)):
            tx = PHOTO_X + i * (TW + PG)
            slot = key.replace('Image', '').lower()
            draw_photo(c, tx, TY, TW, BOT_H,
                       data.get(key, ''), lab, f'（{sub}）',
                       cs=_cs, cr=_cr, mode=fit_mode('2','B',slot))
        callout = (data.get('yieldCallout', '') or '').strip()
        if callout:
            cw  = min(K1_W * 0.50, 130)
            ch_ = 28
            cox = K1_X + K1_W - cw - 8
            coy = K1_Y + TOP_H - ch_ - 8
            c.saveState()
            c.setFillColor(colors.HexColor('#00000022'))
            c.ellipse(cox + 2, coy - 2, cox + cw + 2, coy - 2 + ch_, fill=1, stroke=0)
            c.restoreState()
            c.saveState()
            c.setFillColor(C_YELLOW); c.setStrokeColor(C_RED_DK); c.setLineWidth(1.2)
            c.ellipse(cox, coy, cox + cw, coy + ch_, fill=1, stroke=1)
            c.restoreState()
            csz = autosize(callout, cw - 14, 11, min_sz=6, bold=True, nav_font=_nav_font)
            draw_bold(c, callout, cox + cw/2, coy + ch_/2 - csz * 0.32, csz,
                      color=C_RED_DK, align='center', nav_font=_nav_font)

    # ══════════════════════════════════════════════════════════════════════
    # DETAIL ROWS  (right of frame) — plain text rows, alt-row tint, no nav bar
    # ══════════════════════════════════════════════════════════════════════
    detail_rows_in = data.get('detailRows', []) or []
    detail_rows = [r for r in detail_rows_in
                   if isinstance(r, dict) and (r.get('value') or '').strip()][:20]

    DT_X, DT_Y, DT_W, DT_H = DETAIL_X, IN_Y, DETAIL_W, IN_H
    if detail_rows:
        n = len(detail_rows)
        row_slot = DT_H / n
        ROW_FONT = max(7, min(int(row_slot * 0.45), 9))
        LBL_W    = DT_W * 0.38
        hline(c, DT_X, DT_X + DT_W, DT_Y + DT_H, color=C_CREAM_BD, lw=0.4)
        for i, row in enumerate(detail_rows):
            lbl = (row.get('label', '') or '').strip()
            val = (row.get('value', '') or '').strip()
            ry  = DT_Y + DT_H - (i + 1) * row_slot
            if i % 2 == 1:
                rect(c, DT_X, ry, DT_W, row_slot, fill=C_TINT_BEIGE)
            hline(c, DT_X, DT_X + DT_W, ry, color=C_CREAM_BD, lw=0.3)
            tb = ry + row_slot/2 - ROW_FONT * 0.32
            draw_text(c, truncate_text(lbl, LBL_W - 4, ROW_FONT, bold=True),
                      DT_X + 4, tb, ROW_FONT,
                      color=C_GREEN_DK, bold=True, nav_font=_nav_font)
            draw_text(c, truncate_text(val, DT_W - LBL_W - 4, ROW_FONT),
                      DT_X + LBL_W, tb, ROW_FONT,
                      color=C_BLACK, nav_font=_nav_font)

    # ══════════════════════════════════════════════════════════════════════
    # DISCLAIMER  (single line below frame)
    # ══════════════════════════════════════════════════════════════════════
    draw_text(c, '※ 店頭用資料としてご利用下さい。',
              MX + 2, DISC_BOT + 1.4, 8,
              color=C_GREY_TXT, nav_font=_nav_font)

    # ══════════════════════════════════════════════════════════════════════
    # FOOTER  (white, simple — company name + info columns + ■markers)
    # ══════════════════════════════════════════════════════════════════════
    F_PAD = 4
    hline(c, MX, MX + IW, FOOTER_TOP, color=C_GREY_TXT, lw=0.4)

    logo_b64  = data.get('logoImage', '')
    brand     = (data.get('brandName', '') or '').strip()
    co        = (data.get('companyName', '') or '').strip()
    licenseNo = (data.get('licenseNo', '') or '').strip()
    addr_co   = (data.get('companyAddress', '') or '').strip()
    tel       = (data.get('tel', '') or '').strip()
    fax       = (data.get('fax', '') or '').strip()
    em        = (data.get('email', '') or '').strip()
    ag        = (data.get('agentName', '') or '').strip()
    ag_tel    = (data.get('agentTel', '') or '').strip()
    ttype     = (data.get('transactionType', '') or '').strip()
    fee       = (data.get('fee', '') or '').strip()

    cur_x = MX + F_PAD
    if logo_b64:
        try:
            raw = logo_b64.split(',', 1)[-1] if ',' in logo_b64 else logo_b64
            li  = ImageReader(io.BytesIO(base64.b64decode(raw)))
            lw2, lh2 = li.getSize()
            target_h = FOOTER_H * 0.78
            target_w = target_h * (lw2 / lh2) if lh2 else target_h
            target_w = min(target_w, FOOTER_H)
            c.drawImage(li, cur_x, FOOTER_BOT + (FOOTER_H - target_h)/2,
                        target_w, target_h, preserveAspectRatio=True, mask='auto')
            cur_x += target_w + 6
        except Exception:
            pass

    main_name  = co or brand
    name_avail = IW * 0.32
    if main_name:
        nm_sz = autosize(main_name, name_avail, 22, min_sz=11, bold=True,
                         nav_font=_nav_font)
        nm_y  = FOOTER_BOT + FOOTER_H/2 - nm_sz * 0.32
        draw_bold(c, main_name, cur_x, nm_y, nm_sz,
                  color=C_BLACK, nav_font=_nav_font)
        cur_x += txt_width(main_name, nm_sz, bold=True, nav_font=_nav_font) + 8

    info_x    = cur_x
    markers_w = 145
    info_w    = MX + IW - info_x - F_PAD - markers_w - 4

    info_rows = []
    if licenseNo: info_rows.append(licenseNo)
    if addr_co:   info_rows.append(addr_co)
    line_tf = ''
    if tel and fax: line_tf = f'TEL：{tel}　FAX：{fax}'
    elif tel:       line_tf = f'TEL：{tel}'
    elif fax:       line_tf = f'FAX：{fax}'
    if line_tf:     info_rows.append(line_tf)
    if em:          info_rows.append(f'E-mail：{em}')
    if ag:
        line_ag = f'担当：{ag}'
        if ag_tel: line_ag += f'　携帯：{ag_tel}'
        info_rows.append(line_ag)

    if info_rows:
        ISZ  = 8
        IGAP = 2.4
        n_rows = len(info_rows)
        max_h  = FOOTER_H - 4
        while ISZ > 6 and (n_rows * ISZ + (n_rows - 1) * IGAP) > max_h:
            ISZ -= 0.5
        total_h = n_rows * ISZ + (n_rows - 1) * IGAP
        iy = FOOTER_BOT + (FOOTER_H + total_h) / 2 - ISZ
        for txt in info_rows:
            draw_text(c, truncate_text(txt, info_w, ISZ),
                      info_x, iy, ISZ, color=C_BLACK, nav_font=_nav_font)
            iy -= ISZ + IGAP

    mk_lines = []
    if ttype: mk_lines.append(f'■ 取引態様：{ttype}')
    if fee:   mk_lines.append(f'■ 手数料：{fee}')
    if mk_lines:
        MSZ  = 8
        MGAP = 3
        mk_x = MX + IW - F_PAD - markers_w
        total_h = len(mk_lines) * MSZ + (len(mk_lines) - 1) * MGAP
        my2 = FOOTER_BOT + (FOOTER_H + total_h) / 2 - MSZ
        for txt in mk_lines:
            draw_text(c, truncate_text(txt, markers_w, MSZ),
                      mk_x, my2, MSZ, color=C_BLACK, nav_font=_nav_font)
            my2 -= MSZ + MGAP


# ── Vercel handler ────────────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        for k, v in [('Access-Control-Allow-Origin','*'),
                     ('Access-Control-Allow-Methods','POST, OPTIONS'),
                     ('Access-Control-Allow-Headers','Content-Type')]:
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        try:
            n   = int(self.headers.get('Content-Length', 0))
            dat = json.loads(self.rfile.read(n))
            buf = io.BytesIO()
            generate(dat, buf)
            pdf = buf.getvalue()
            self.send_response(200)
            for k, v in [('Content-Type','application/pdf'),
                         ('Content-Disposition','attachment; filename="flyer.pdf"'),
                         ('Content-Length', str(len(pdf))),
                         ('Access-Control-Allow-Origin','*')]:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(pdf)
        except Exception as e:
            msg = str(e).encode()
            self.send_response(500)
            self.send_header('Content-Type','text/plain')
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, *a): pass


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python generate_flyer.py data.json output.pdf'); sys.exit(1)
    with open(sys.argv[1], encoding='utf-8') as f:
        generate(json.load(f), sys.argv[2])
