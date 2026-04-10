"""
generate_flyer.py  —  Justsalemono  (Template 1)
─────────────────────────────────────────────────────────────
A4 landscape.  Three columns, four cells in the right area:

  LEFT (≈24%)  │  Q1 (38%)        │  Q2 (38%)
  ─────────────┼──────────────────┼──────────────────
  TOP BAND     │  K1 外観写真      │  K5 地図          ← Variant A
  (title/      │                  │  or K2 photo      ← Variant B
   price)      │                  │  [promo ribbon ▶]
  ─────────────┼──────────────────┼──────────────────
  data rows    │  H/I 周辺環境     │  K2 間取り図       ← Variant A
               │  (flowing text)  │  K3/K4 photo      ← Variant B
  ─────────────┴──────────────────┴──────────────────
  FOOTER  (IW width — Logo | Name | Info | Contact | Yellow)

ly convention: ly = current TOP-EDGE; helpers decrement BEFORE drawing.
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

# ── Font ──────────────────────────────────────────────────────────────────────
def _resolve_font():
    for p in [
        os.environ.get('FONT_PATH', ''),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'fonts', 'DroidSansFallbackFull.ttf'),
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError('DroidSansFallbackFull.ttf not found.')

JP_FONT = 'JP'
LA_FONT = 'Helvetica'
LA_BOLD = 'Helvetica-Bold'
pdfmetrics.registerFont(TTFont(JP_FONT, _resolve_font()))

# ── Text engine ───────────────────────────────────────────────────────────────
def is_latin(ch): return ord(ch) <= 0x00FF

def txt_width(s, size, bold=False):
    return sum(pdfmetrics.stringWidth(ch, (LA_BOLD if bold else LA_FONT)
               if is_latin(ch) else JP_FONT, size) for ch in s)

def draw_text(c, s, x, y, size, color=None, align='left', bold=False):
    if not s: return
    if color: c.setFillColor(color)
    if align in ('center', 'right'):
        w = txt_width(s, size, bold)
        x = (x - w/2) if align == 'center' else (x - w)
    cur_x, run, run_lat = x, '', None
    def flush(seg, lat, cx):
        if not seg: return cx
        f = (LA_BOLD if lat else JP_FONT) if bold else (LA_FONT if lat else JP_FONT)
        c.setFont(f, size); c.drawString(cx, y, seg)
        return cx + pdfmetrics.stringWidth(seg, f, size)
    for ch in s:
        lat = is_latin(ch)
        if run_lat is None: run_lat = lat
        if lat != run_lat: cur_x = flush(run, run_lat, cur_x); run, run_lat = ch, lat
        else: run += ch
    flush(run, run_lat, cur_x)

def draw_bold(c, s, x, y, size, color=None, align='left'):
    draw_text(c, s, x, y, size, color, align, bold=True)

def _draw_rotated_text(c, s, x, y, size):
    """Draw mixed JP/Latin text at position (x,y) in the CURRENT (rotated) coordinate space."""
    if not s: return
    cur_x = x
    run, run_lat = '', None
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
    if not s or txt_width(s, size, bold) <= max_w:
        return s
    for i in range(len(s), 0, -1):
        cand = s[:i] + ellipsis
        if txt_width(cand, size, bold) <= max_w:
            return cand
    return ellipsis

# ── Colours ───────────────────────────────────────────────────────────────────
C_NAVY   = colors.HexColor('#1a4fa0')
C_NAVYDK = colors.HexColor('#12357a')
C_ACCENT = colors.HexColor('#e85d2f')
C_WHITE  = colors.white
C_BLACK  = colors.HexColor('#1c2333')
C_MUTED  = colors.HexColor('#5a6480')
C_LBLUE  = colors.HexColor('#eef3fb')
C_MBLUE  = colors.HexColor('#d8e4f5')
C_SECBG  = colors.HexColor('#dde8f8')
C_DIV    = colors.HexColor('#c0cfe8')
C_STEELBL= colors.HexColor('#adc4e8')
C_DARKBL = colors.HexColor('#c8d8f0')
C_RED    = colors.HexColor('#dc2626')
C_AMBER  = colors.HexColor('#f9d87a')
C_REDBG  = colors.HexColor('#fef2f2')
C_REDBDR = colors.HexColor('#f87171')

# ── Primitives ────────────────────────────────────────────────────────────────
def rect(c, x, y, w, h, fill=None, stroke=None, lw=0.5):
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(lw)
    c.rect(x, y, w, h, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()

def vline(c, x, y1, y2, color=C_DIV, lw=0.4):
    c.saveState(); c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x, y1, x, y2); c.restoreState()

def hline(c, x1, x2, y, color=C_DIV, lw=0.4):
    c.saveState(); c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x1, y, x2, y); c.restoreState()

def photo_placeholder(c, x, y, w, h, label, sublabel='', bg='#c8d4e8', tc='#7a8faa'):
    """Draw a shaded photo slot with centred labels."""
    rect(c, x, y, w, h, fill=colors.HexColor(bg), stroke=C_DIV, lw=0.5)
    cx = x + w / 2
    draw_text(c, label,    cx, y + h/2 + 6,  12, color=colors.HexColor(tc), align='center')
    if sublabel:
        draw_text(c, sublabel, cx, y + h/2 - 9, 7.5, color=colors.HexColor(tc), align='center')

def draw_photo(c, x, y, w, h, b64_data, label, sublabel=''):
    """Draw a real photo (JPEG/PNG base64) or fall back to placeholder."""
    if b64_data:
        try:
            raw = b64_data.split(',', 1)[-1] if ',' in b64_data else b64_data
            img_bytes = base64.b64decode(raw)
            img = ImageReader(io.BytesIO(img_bytes))
            iw, ih = img.getSize()
            scale = min(w / iw, h / ih)
            dw, dh = iw * scale, ih * scale
            ox = x + (w - dw) / 2
            oy = y + (h - dh) / 2
            c.saveState()
            cp = c.beginPath(); cp.rect(x, y, w, h); c.clipPath(cp, stroke=0)
            c.drawImage(img, ox, oy, dw, dh, preserveAspectRatio=True, mask='auto')
            c.restoreState()
            return
        except Exception:
            pass
    photo_placeholder(c, x, y, w, h, label, sublabel)

def _img_ar(b64_data, default=4/3):
    """Return aspect ratio (w/h) of a base64 image, or default."""
    if b64_data:
        try:
            raw = b64_data.split(',', 1)[-1] if ',' in b64_data else b64_data
            img = ImageReader(io.BytesIO(base64.b64decode(raw)))
            iw, ih = img.getSize()
            return iw / ih if ih else default
        except Exception:
            pass
    return default

def draw_flex_grid(c, images, x, y, w, h):
    """
    Flexible photo grid — aspect-ratio-aware layout for 1–4 images.
    White gaps between cells create a shadow/mat effect.
    images: list of (b64, label, sublabel) tuples.
    """
    GAP = 3   # white gap between photos (shadow/mat effect)
    n = len(images)
    if n == 0:
        return
    ars = [_img_ar(b) for b, _, _ in images]

    def row(imgs, ars_r, rx, ry, rw, rh):
        """Draw one row of images side-by-side with white gaps."""
        n_imgs = len(imgs)
        usable_w = rw - GAP * (n_imgs - 1)
        total = sum(ars_r) or 1
        cur_x = rx
        for i, (img_tuple, ar) in enumerate(zip(imgs, ars_r)):
            cell_w = usable_w * ar / total
            if i == n_imgs - 1:
                cell_w = rx + rw - cur_x   # last cell absorbs rounding
            draw_photo(c, cur_x, ry, cell_w, rh, *img_tuple)
            cur_x += cell_w
            if i < n_imgs - 1:
                rect(c, cur_x, ry, GAP, rh, fill=C_WHITE)
                cur_x += GAP

    if n == 1:
        draw_photo(c, x, y, w, h, *images[0])

    elif n == 2:
        row(images, ars, x, y, w, h)

    elif n == 3:
        rh0_nat = w / ars[0]
        rh1_nat = w / ((ars[1] + ars[2]) / 2)
        tot = rh0_nat + rh1_nat or 1
        rh0 = max(h * 0.35, min(h * 0.65, h * rh0_nat / tot))
        rh1 = h - rh0 - GAP
        draw_photo(c, x, y + rh1 + GAP, w, rh0, *images[0])
        rect(c, x, y + rh1, w, GAP, fill=C_WHITE)
        row(images[1:], ars[1:], x, y, w, rh1)

    else:  # n == 4
        avg_top = (ars[0] + ars[1]) / 2
        avg_bot = (ars[2] + ars[3]) / 2
        rh_top_nat = w / avg_top
        rh_bot_nat = w / avg_bot
        tot = rh_top_nat + rh_bot_nat or 1
        rh_top = max(h * 0.35, min(h * 0.65, h * rh_top_nat / tot))
        rh_bot = h - rh_top - GAP
        row(images[:2], ars[:2], x, y + rh_bot + GAP, w, rh_top)
        rect(c, x, y + rh_bot, w, GAP, fill=C_WHITE)
        row(images[2:], ars[2:], x, y, w, rh_bot)


# ── Generator ─────────────────────────────────────────────────────────────────
def generate(data: dict, out):
    PAGE = landscape(A4)         # A4 landscape (841 × 595 pts) — always
    c = canvas.Canvas(out, pagesize=PAGE)
    W, H = PAGE                  # W ≈ 841.89,  H ≈ 595.28
    MX = 10 * mm
    MY = 7  * mm
    IW = W - 2 * MX             # ≈ 822 pts

    variant = data.get('templateVariant', 'A').upper()

    # ── Font/size constants ───────────────────────────────────────────────────
    PILL_SZ = 10          # property type pill font size
    ST_FONT = PILL_SZ     # Change 3: station info same size as pill

    # ── Column geometry ───────────────────────────────────────────────────────
    # Change 1: reduce left column by another 15% (on top of previous 15%)
    LCW  = IW * 0.34 * 0.85 * 0.85   # ≈ IW * 0.245
    RW   = IW - LCW
    LX   = MX
    RX   = LX + LCW

    HALF = RW / 2
    RX1  = RX
    RX2  = RX + HALF

    # ── Vertical anchors ──────────────────────────────────────────────────────
    # Change 4: footer height ×1.5 (18mm → 27mm); constrained to IW
    FOOTER_H  = 27 * mm
    FOOTER_Y  = MY

    CTOP      = H - MY
    CBOT      = MY + FOOTER_H + 2 * mm

    # ── Read station data early (needed for ST_H geometry) ───────────────────
    stations_raw = data.get('stations', [])[:3]
    n_st = max(len(stations_raw), 1)
    ST_H = n_st * (ST_FONT + 3) + 4   # dynamic station strip height

    # ── Change 2: Nav box height = just enough for propertyName + pill + address ─
    pill_pad_x, pill_pad_y = 8, 4
    pill_bh = PILL_SZ + pill_pad_y * 2   # = 18 pts

    prop_type_early  = data.get('propertyType', '中古戸建')
    prop_name_early  = data.get('propertyName', '')
    addr_raw_early   = data.get('address', '')
    short_early      = addr_raw_early.replace('東京都','').replace('大阪府','').replace('神奈川県','')[:20]

    # Auto-size property name font
    prop_name_sz = 0
    if prop_name_early:
        for sz in range(20, 7, -1):
            if txt_width(prop_name_early, sz, bold=True) <= LCW - 10:
                prop_name_sz = sz; break

    addr_sz_early = 8
    for sz in range(22, 7, -1):
        if txt_width(short_early, sz, bold=True) <= LCW - 10:
            addr_sz_early = sz; break

    # NAV_H: propertyName (if any) + pill + address + internal padding
    NAV_H_base = pill_bh + addr_sz_early + 14
    NAV_H = NAV_H_base + (prop_name_sz + 8 if prop_name_sz else 0)

    PRICE_H = 20 * mm

    # Right area vertical split
    CONTENT_H = CTOP - CBOT
    TOP_H     = CONTENT_H * 0.48
    BAND_TOP  = CTOP
    BAND_BOT  = CTOP - TOP_H

    MID_TOP   = BAND_BOT
    MID_BOT   = CBOT
    MID_H     = MID_TOP - MID_BOT

    # ─────────────────────────────────────────────────────────────────────────
    # TOP BAND — LEFT column:  NAVY (type+address)  /  STATION STRIP  /  PRICE
    # ─────────────────────────────────────────────────────────────────────────

    # ── Navy header box — propertyName (headline) + pill + address, centered ──
    nav_y = BAND_BOT + PRICE_H + ST_H      # bottom of navy box (in PDF y-space)
    rect(c, LX, nav_y, LCW, NAV_H, fill=C_NAVY)

    prop_type = data.get('propertyType', '中古戸建')
    prop_name = prop_name_early
    bw = txt_width(prop_type, PILL_SZ) + pill_pad_x * 2
    bh = pill_bh
    nav_top = nav_y + NAV_H   # visual top of navy box

    # ── Property name headline at the very top ────────────────────────────────
    if prop_name and prop_name_sz:
        pname_y = nav_top - prop_name_sz - 5   # text baseline
        draw_bold(c, prop_name, LX + LCW / 2, pname_y, prop_name_sz,
                  color=C_WHITE, align='center')
        # Gold accent line below name
        hline(c, LX + 4, LX + LCW - 4, pname_y - 3,
              color=colors.HexColor('#f9d87a'), lw=0.7)
        # Pill positioned just below the accent line
        by = pname_y - 3 - 5 - bh
    else:
        # No property name: pill near top as before
        by = nav_top - bh - 5

    # ── Type pill — centered horizontally ────────────────────────────────────
    pill_x = LX + (LCW - bw) / 2
    rect(c, pill_x, by, bw, bh, fill=C_ACCENT)
    draw_text(c, prop_type, pill_x + pill_pad_x, by + pill_pad_y, PILL_SZ, color=C_WHITE)

    # ── Address: centered in space below pill ─────────────────────────────────
    addr_raw = addr_raw_early
    short    = short_early
    addr_sz  = addr_sz_early
    space_below_pill = by - nav_y
    addr_y   = nav_y + (space_below_pill - addr_sz) / 2
    draw_bold(c, short, LX + LCW / 2, addr_y, addr_sz, color=C_WHITE, align='center')

    # ── Station strip — Change 3: ST_FONT=PILL_SZ=10, center-aligned ─────────
    rect(c, LX, BAND_BOT + PRICE_H, LCW, ST_H, fill=colors.HexColor('#dce8f8'))
    addr_avail = LCW - 10
    st_y = BAND_BOT + PRICE_H + ST_H - ST_FONT - 2
    for st in stations_raw:
        if st_y < BAND_BOT + PRICE_H + 2: break
        ln  = st.get('line', '')
        stn = st.get('station', '').replace('駅', '')
        wk  = st.get('walk', '')
        line_t = truncate_text(f"{ln}　{stn}駅 徒歩{wk}分", addr_avail, ST_FONT)
        draw_text(c, line_t, LX + LCW / 2, st_y, ST_FONT, color=C_NAVY, align='center')
        st_y -= ST_FONT + 3

    # ── Price strip ───────────────────────────────────────────────────────────
    rect(c, LX, BAND_BOT, LCW, PRICE_H, fill=C_LBLUE)

    price_raw = data.get('price', '')
    num_part  = price_raw.replace('万円', '').strip()
    tax_lbl   = '万円（税込）' if '税込' in data.get('taxIncluded', '税込') else '万円（税別）'
    tax_sz    = ST_FONT

    price_avail_w = LCW - 10
    price_sz = 10
    for sz in range(48, 9, -1):
        combo_w = txt_width(num_part, sz, bold=True) + txt_width(tax_lbl, tax_sz, bold=True) + 4
        if combo_w <= price_avail_w and sz <= PRICE_H * 0.80:
            price_sz = sz; break

    price_y = BAND_BOT + (PRICE_H - price_sz) / 2
    combo_w = txt_width(num_part, price_sz, bold=True) + txt_width(tax_lbl, tax_sz, bold=True) + 4
    price_x = LX + (LCW - combo_w) / 2
    draw_bold(c, num_part, price_x, price_y, price_sz, color=C_ACCENT)
    draw_text(c, tax_lbl,
              price_x + txt_width(num_part, price_sz, bold=True) + 4,
              price_y + 2, tax_sz, color=C_ACCENT)
    draw_text(c, '販売価格', LX + 5, BAND_BOT + PRICE_H - 8, 5.5, color=C_MUTED)

    rebuild = data.get('rebuild', '')
    if rebuild:
        rbw = txt_width(rebuild, 7) + 10
        rect(c, LX + LCW - rbw - 4, BAND_BOT + PRICE_H - 13, rbw, 11,
             fill=C_REDBG, stroke=C_REDBDR, lw=0.6)
        draw_text(c, rebuild, LX + LCW - rbw/2 - 4, BAND_BOT + PRICE_H - 10, 7,
                  color=C_RED, align='center')

    # ─────────────────────────────────────────────────────────────────────────
    # RIGHT PHOTO AREA
    # ─────────────────────────────────────────────────────────────────────────
    if variant == 'B':
        b_images = [
            (data.get('k1Image',''), '外　観',      '（K1）'),
            (data.get('k2Image',''), '外観写真２',  '（K2）'),
            (data.get('k3Image',''), '外観写真３',  '（K3）'),
            (data.get('k4Image',''), '間取り / 地図', '（K4）'),
        ]
        draw_flex_grid(c, b_images, RX, MID_BOT, RW, CONTENT_H)

    rect(c, RX, MID_BOT, RW, CONTENT_H, fill=None, stroke=C_DIV, lw=0.5)

    # ─────────────────────────────────────────────────────────────────────────
    # VARIANT A — TOP BAND PHOTOS
    # ─────────────────────────────────────────────────────────────────────────
    lease    = data.get('leasePeriod', '')
    grent    = data.get('groundRent', '')
    status   = data.get('currentStatus', '')
    handover = data.get('handover', '')

    if variant != 'B':
        draw_photo(c, RX1, BAND_BOT, HALF, TOP_H,
                   data.get('k1Image', ''), '外　観', '（写真をここに挿入）')
        draw_photo(c, RX2, BAND_BOT, HALF, TOP_H,
                   data.get('k5Image', ''), '地　図', '（地図を挿入）')

    if variant != 'B':
        # Q1-bottom: H/I 周辺環境・学区 info box
        rect(c, RX1, MID_BOT, HALF, MID_H,
             fill=colors.HexColor('#f0f5ff'), stroke=C_DIV, lw=0.5)

        q2y    = MID_BOT + MID_H - 4
        q2_pad = 4
        q2_inner_w = HALF - q2_pad * 2

        # G — 借地条件
        if lease or grent:
            g_bar_h = 11
            if q2y - g_bar_h >= MID_BOT:
                q2y -= g_bar_h
                rect(c, RX1, q2y, HALF, g_bar_h, fill=C_NAVY)
                draw_bold(c, '借地条件', RX1 + q2_pad, q2y + 3, 6.5, color=C_WHITE)
            if grent and q2y - 10 >= MID_BOT:
                q2y -= 10
                draw_text(c, f'地代　{grent}', RX1 + q2_pad, q2y + 2, 6.5, color=C_BLACK)
            if lease and q2y - 9 >= MID_BOT:
                q2y -= 9
                draw_text(c, truncate_text(lease, q2_inner_w, 6.5), RX1 + q2_pad, q2y + 2, 6.5, color=C_BLACK)
            if (status or handover) and q2y - 10 >= MID_BOT:
                q2y -= 2
                rect(c, RX1, q2y - 10, HALF, 10, fill=C_MBLUE)
                draw_text(c, f'現況:{status}　引渡:{handover}', RX1 + q2_pad, q2y - 7, 6, color=C_NAVY)
                q2y -= 12
            q2y -= 4

        # H — 周辺環境 (Change 7: flowing word text, not table)
        nearby = data.get('nearby', [])
        if nearby and q2y - 11 >= MID_BOT:
            q2y -= 11
            rect(c, RX1, q2y, HALF, 11, fill=C_NAVY)
            draw_bold(c, '■ 周辺環境', RX1 + q2_pad, q2y + 3, 6.5, color=C_WHITE)

        if nearby:
            nearby_sz  = 7
            line_h     = nearby_sz + 3
            SEP        = '　・　'
            avail_w    = HALF - q2_pad * 2

            # Wrap items into lines at separator boundaries
            parts = [f"{nb.get('name','')}({nb.get('walk','')})"
                     for nb in nearby if nb.get('name')]
            lines_nb = []
            cur_line  = ''
            for i, part in enumerate(parts):
                chunk = (SEP if cur_line else '') + part
                if cur_line and txt_width(cur_line + chunk, nearby_sz) > avail_w:
                    lines_nb.append(cur_line)
                    cur_line = part
                else:
                    cur_line += chunk
            if cur_line:
                lines_nb.append(cur_line)

            for line in lines_nb[:5]:
                if q2y - line_h < MID_BOT: break
                q2y -= line_h
                draw_text(c, line, RX1 + q2_pad, q2y + 2, nearby_sz, color=C_BLACK)

        # I — 学区
        school_lines = []
        if data.get('elemSchool'):
            school_lines.append(('小', data['elemSchool'], data.get('elemSchoolDist','')))
        if data.get('juniorSchool'):
            school_lines.append(('中', data['juniorSchool'], data.get('juniorSchoolDist','')))
        if school_lines and q2y - 11 >= MID_BOT:
            q2y -= 15
            rect(c, RX1, q2y, HALF, 11, fill=C_NAVY)
            draw_bold(c, '■ 学区', RX1 + q2_pad, q2y + 3, 6.5, color=C_WHITE)
        for i, (tag, nm, dist) in enumerate(school_lines):
            if q2y - 10 < MID_BOT: break
            q2y -= 10
            bg = C_LBLUE if i % 2 == 1 else C_WHITE
            rect(c, RX1, q2y, HALF, 10, fill=bg, stroke=C_DIV, lw=0.2)
            nm_t = truncate_text(f'{tag}:  {nm}', q2_inner_w * 0.62, 6.5)
            draw_text(c, nm_t, RX1 + q2_pad, q2y + 2, 6.5, color=C_BLACK)
            draw_text(c, dist, RX1 + HALF - q2_pad, q2y + 2, 6, color=C_MUTED, align='right')

    # ─────────────────────────────────────────────────────────────────────────
    # SPECIAL PROMO — 绶带 (diagonal corner ribbon) top-right
    # Change 6: auto-scale 'a' to hold up to 20 characters; center-aligned
    # ─────────────────────────────────────────────────────────────────────────
    promo = data.get('specialPromo', '').strip()
    if promo:
        cx_r = W - MX
        cy_t = CTOP

        ribbon_sz  = 7.5
        promo_tw   = txt_width(promo, ribbon_sz, bold=True)
        # The ribbon text runs at -45°; available diagonal length ≈ a*√2
        # Solve for a: a*√2 ≥ promo_tw + margin → a = promo_tw/√2 + margin
        a  = max(55, int(promo_tw / math.sqrt(2)) + 20)
        bw = max(28, int(a * 0.55))

        P1 = (cx_r - a,      cy_t)
        P2 = (cx_r - a + bw, cy_t)
        P3 = (cx_r,          cy_t - a + bw)
        P4 = (cx_r,          cy_t - a)

        c.saveState()
        clip = c.beginPath()
        clip.rect(RX, CBOT, RW, CONTENT_H)
        c.clipPath(clip, stroke=0)

        # Shadow
        c.setFillColor(colors.HexColor('#c0000066'))
        ps = c.beginPath()
        ps.moveTo(P1[0]+2, P1[1]-2); ps.lineTo(P2[0]+2, P2[1]-2)
        ps.lineTo(P3[0]+2, P3[1]-2); ps.lineTo(P4[0]+2, P4[1]-2)
        ps.close(); c.drawPath(ps, fill=1, stroke=0)

        # Ribbon body
        c.setFillColor(C_RED)
        pr = c.beginPath()
        pr.moveTo(*P1); pr.lineTo(*P2); pr.lineTo(*P3); pr.lineTo(*P4)
        pr.close(); c.drawPath(pr, fill=1, stroke=0)

        # Gold border lines
        c.setStrokeColor(C_AMBER); c.setLineWidth(0.8)
        c.line(*P1, *P4); c.line(*P2, *P3)

        # Rotated text — center-aligned in ribbon midpoint
        mid_x = (P1[0] + P3[0]) / 2
        mid_y = (P1[1] + P3[1]) / 2
        c.translate(mid_x, mid_y); c.rotate(-45)
        c.setFillColor(C_WHITE)
        _draw_rotated_text(c, promo, -promo_tw / 2, -ribbon_sz / 2, ribbon_sz)
        c.restoreState()

    # ─────────────────────────────────────────────────────────────────────────
    # GRID DIVIDERS (Variant A only)
    # ─────────────────────────────────────────────────────────────────────────
    vline(c, RX, CBOT, CTOP, color=C_DIV, lw=0.8)
    if variant != 'B':
        vline(c, RX2, CBOT, CTOP, color=C_DIV, lw=0.5)
        hline(c, RX, W - MX, BAND_BOT, color=C_DIV, lw=0.6)

    # ─────────────────────────────────────────────────────────────────────────
    # MIDDLE SECTION — LEFT column  (property data rows)
    # ─────────────────────────────────────────────────────────────────────────
    rect(c, LX, MID_BOT, LCW, MID_H, fill=C_WHITE)

    LLBW = LCW * 0.34
    LVBW = LCW - LLBW
    LRH  = 13
    LBAR = 12

    ly = MID_TOP

    def lsec(title):
        nonlocal ly
        if ly - LBAR < MID_BOT: return
        ly -= LBAR
        rect(c, LX, ly, LCW, LBAR, fill=C_NAVY)
        draw_bold(c, title, LX + 4, ly + 3, 7, color=C_WHITE)

    def lrow(lbl, val, alt=False):
        nonlocal ly
        if not val: return
        if ly - LRH < MID_BOT: return
        ly -= LRH
        bg = C_LBLUE if alt else C_WHITE
        rect(c, LX,         ly, LLBW, LRH, fill=C_SECBG, stroke=C_DIV, lw=0.3)
        draw_text(c, lbl,   LX + 2,         ly + 3, 6.5, color=C_NAVY)
        rect(c, LX + LLBW,  ly, LVBW, LRH, fill=bg,     stroke=C_DIV, lw=0.3)
        val_fit = truncate_text(val, LVBW - 5, 6.5)
        draw_text(c, val_fit, LX + LLBW + 3, ly + 3, 6.5, color=C_BLACK)

    lsec('■ 所在地')
    lrow('所在地', addr_raw)

    lsec('■ 物件概要')

    la = f"{data.get('landArea','')}㎡"
    if data.get('landAreaTsubo'):
        la += f"  ({data['landAreaTsubo']}坪)"

    fa_parts = [data.get(f'floorArea{i}','') for i in range(1,5)]
    fa = '  '.join(x for x in fa_parts if x)
    tf = f"{data.get('totalFloorArea','')}㎡" if data.get('totalFloorArea') else ''

    lrow('土地面積', la)
    lrow('土地権利', data.get('landRight',''),      alt=True)
    lrow('地目',     data.get('landCategory',''))
    lrow('接面道路', data.get('frontRoad',''),       alt=True)
    lrow('再建築',   rebuild)
    lrow('築年月',   data.get('builtYear',''),       alt=True)
    lrow('構造',     data.get('structure',''))
    lrow('床面積',   fa if fa else '',               alt=True)
    if tf: lrow('合計', tf)
    lrow('間取り',   data.get('layout',''),          alt=True)
    lrow('現況',     status)
    lrow('引渡し',   handover,                       alt=True)

    if data.get('propertyType','') == 'マンション':
        lsec('■ マンション情報')
        lrow('建物名',   data.get('buildingName',''))
        lrow('所在階',   data.get('floorInfo',''),     alt=True)
        lrow('専有面積', f"{data.get('exclusiveArea','')}㎡" if data.get('exclusiveArea') else '')
        lrow('バルコニー', f"{data.get('balconyArea','')}㎡" if data.get('balconyArea') else '', alt=True)
        lrow('管理費',   f"{data.get('managementFee','')}円/月" if data.get('managementFee') else '')
        lrow('修繕積立', f"{data.get('repairFund','')}円/月"    if data.get('repairFund') else '',  alt=True)
        lrow('管理会社', data.get('managementCo',''))
        lrow('管理形態', data.get('managementType',''), alt=True)

    if data.get('propertyType','') != 'マンション':
        lsec('■ 法令制限')
        lrow('都市計画', data.get('cityPlan',''))
        lrow('用途地域', data.get('useZone',''),         alt=True)
        lrow('防火指定', data.get('fireZone',''))
        lrow('建ぺい率', data.get('bcr',''),             alt=True)
        lrow('容積率',   data.get('far',''))
        lrow('高度地区', data.get('heightDistrict',''),  alt=True)
        if data.get('otherLegal'):
            lrow('その他', data['otherLegal'])

    up_parts = []
    if data.get('electric'): up_parts.append(f"電気：{data['electric']}")
    if data.get('gas'):      up_parts.append(f"ガス：{data['gas']}")
    if data.get('water'):    up_parts.append(f"水道：{data['water']}")
    if up_parts:
        lsec('■ ライフライン')
        if ly - LRH >= MID_BOT:
            ly -= LRH
            rect(c, LX, ly, LCW, LRH, fill=C_WHITE, stroke=C_DIV, lw=0.3)
            up_fit = truncate_text('　'.join(up_parts), LCW - 6, 6.5)
            draw_text(c, up_fit, LX + 3, ly + 3, 6.5, color=C_BLACK)

    DISCLAIMER = '現況と図面が相違する場合は現況を優先します'
    remarks = [r.strip() for r in data.get('remarks','').split('\n')
               if r.strip() and DISCLAIMER not in r]
    if remarks:
        lsec('■ 備考')
        for i, r in enumerate(remarks):
            lrow('', r, alt=(i % 2 == 1))

    if MID_BOT + 8 < ly:
        draw_text(c, '※現況と図面が相違する場合は現況を優先します。',
                  LX + 2, MID_BOT + 4, 5.5, color=C_MUTED)

    # ─────────────────────────────────────────────────────────────────────────
    # Q2-bottom (Variant A): K2 間取り図
    # ─────────────────────────────────────────────────────────────────────────
    if variant != 'B':
        draw_photo(c, RX2, MID_BOT, HALF, MID_H,
                   data.get('k2Image', ''), '間取り図', '（間取り図を挿入）')

    # ─────────────────────────────────────────────────────────────────────────
    # FOOTER — Changes 4 & 5:
    #   Width constrained to IW (MX … W-MX); height = 27mm
    #   Order left→right: Logo | Name | Info | Contact | Yellow
    # ─────────────────────────────────────────────────────────────────────────
    F_PAD    = 5
    FY_TOP   = FOOTER_Y + FOOTER_H
    DIV_COL  = colors.HexColor('#2a4a8a')

    # Section widths — proportional to IW
    F_LOGO_W = FOOTER_H              # a: square logo (27mm × 27mm)
    F_NAME_W = IW * 0.17             # b: company name
    F_INFO_W = IW * 0.22             # c: company info
    F_CONT_W = IW * 0.24             # d: contact
    F_YELL_W = IW - F_LOGO_W - F_NAME_W - F_INFO_W - F_CONT_W  # e: yellow

    # x positions: left→right = Logo | Name | Info | Contact | Yellow
    F_LOGO_X = MX
    F_NAME_X = MX + F_LOGO_W
    F_INFO_X = MX + F_LOGO_W + F_NAME_W
    F_CONT_X = MX + F_LOGO_W + F_NAME_W + F_INFO_W
    F_YELL_X = MX + F_LOGO_W + F_NAME_W + F_INFO_W + F_CONT_W

    # Navy background (IW width only)
    rect(c, MX, FOOTER_Y, IW, FOOTER_H, fill=C_NAVYDK)

    # ── a) LOGO — leftmost square ─────────────────────────────────────────────
    logo_b64 = data.get('logoImage', '')
    if logo_b64:
        try:
            raw = logo_b64.split(',', 1)[-1] if ',' in logo_b64 else logo_b64
            logo_img = ImageReader(io.BytesIO(base64.b64decode(raw)))
            lw2, lh2 = logo_img.getSize()
            scale = min(F_LOGO_W / lw2, FOOTER_H / lh2) * 0.88 if lw2 and lh2 else 1
            dw, dh = lw2 * scale, lh2 * scale
            c.drawImage(logo_img,
                        F_LOGO_X + (F_LOGO_W - dw) / 2,
                        FOOTER_Y + (FOOTER_H - dh) / 2,
                        dw, dh, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    vline(c, F_NAME_X, FOOTER_Y, FY_TOP, color=DIV_COL, lw=0.6)

    # ── b) COMPANY NAME ────────────────────────────────────────────────────────
    brand = data.get('brandName', '')
    co    = data.get('companyName', '')
    longest_co = max((brand, co), key=len) if (brand or co) else ''
    name_sz = 8
    for sz in range(int(FOOTER_H * 0.62), 7, -1):
        if txt_width(longest_co, sz, bold=True) <= F_NAME_W - F_PAD * 2:
            name_sz = sz; break
    nfy = FY_TOP - F_PAD
    if brand:
        draw_bold(c, brand, F_NAME_X + F_PAD, nfy, name_sz, color=C_WHITE)
        nfy -= name_sz + 3
    if co and co != brand:
        draw_bold(c, co, F_NAME_X + F_PAD, nfy, max(name_sz - 3, 7), color=C_WHITE)

    vline(c, F_INFO_X, FOOTER_Y, FY_TOP, color=DIV_COL, lw=0.6)

    # ── c) COMPANY INFO ────────────────────────────────────────────────────────
    INFO_SZ   = 6.5
    addr_co   = data.get('companyAddress', '')
    tel       = data.get('tel', '')
    fax       = data.get('fax', '')
    em        = data.get('email', '')
    dept      = data.get('department', '')
    licenseNo = data.get('licenseNo', '')
    assoc     = data.get('association', '')
    ify = FY_TOP - F_PAD
    if dept:
        draw_text(c, dept,              F_INFO_X + F_PAD, ify, INFO_SZ, color=colors.HexColor('#aabbd4')); ify -= INFO_SZ + 3
    if addr_co:
        draw_text(c, addr_co,           F_INFO_X + F_PAD, ify, INFO_SZ, color=C_STEELBL); ify -= INFO_SZ + 3
    if tel:
        draw_text(c, f'TEL：{tel}',     F_INFO_X + F_PAD, ify, INFO_SZ, color=C_STEELBL); ify -= INFO_SZ + 3
    if fax:
        draw_text(c, f'FAX：{fax}',     F_INFO_X + F_PAD, ify, INFO_SZ, color=C_STEELBL); ify -= INFO_SZ + 3
    if em:
        draw_text(c, f'✉ {em}',        F_INFO_X + F_PAD, ify, INFO_SZ, color=C_STEELBL); ify -= INFO_SZ + 3
    if licenseNo:
        draw_text(c, licenseNo,         F_INFO_X + F_PAD, ify, INFO_SZ - 0.5, color=colors.HexColor('#8aa8cc')); ify -= INFO_SZ + 2
    if assoc:
        lic_fit = truncate_text(assoc, F_INFO_W - F_PAD * 2, INFO_SZ - 1)
        draw_text(c, lic_fit,           F_INFO_X + F_PAD, ify, INFO_SZ - 1, color=colors.HexColor('#8aa8cc'))

    vline(c, F_CONT_X, FOOTER_Y, FY_TOP, color=DIV_COL, lw=0.6)

    # ── d) CONTACT — orange overhead + agent name + TEL ───────────────────────
    OBC_H = 13
    rect(c, F_CONT_X, FY_TOP - OBC_H, F_CONT_W, OBC_H, fill=C_ACCENT, stroke=None)
    draw_bold(c, 'お問い合わせ先',
              F_CONT_X + F_CONT_W / 2, FY_TOP - OBC_H + 2.5, 9, color=C_WHITE, align='center')

    ag     = data.get('agentName', '')
    ag_tel = data.get('agentTel', '')
    CW     = F_CONT_W - F_PAD * 2
    cy     = FY_TOP - OBC_H - 3

    ag_sz = 8
    if ag:
        for sz in range(min(name_sz, 15), 7, -1):
            if txt_width(f'【担当】{ag}', sz, bold=True) <= CW:
                ag_sz = sz; break
        draw_bold(c, f'【担当】{ag}', F_CONT_X + F_PAD, cy, ag_sz, color=C_WHITE)
        cy -= ag_sz + 3

    tel_str = ag_tel or tel
    tel_sz  = 8
    if tel_str:
        for sz in range(min(name_sz, 16), 7, -1):
            if txt_width(f'TEL：{tel_str}', sz, bold=True) <= CW:
                tel_sz = sz; break
        draw_bold(c, f'TEL：{tel_str}', F_CONT_X + F_PAD, cy, tel_sz, color=C_WHITE)

    vline(c, F_YELL_X, FOOTER_Y, FY_TOP, color=DIV_COL, lw=0.6)

    # ── e) YELLOW SLOGAN AREA — rightmost ─────────────────────────────────────
    rect(c, F_YELL_X, FOOTER_Y, F_YELL_W, FOOTER_H,
         fill=colors.HexColor('#f5c800'), stroke=None)

    # 'catchcopy' is the form field name; 'companySlogan' kept as fallback
    slogan = data.get('catchcopy', data.get('companySlogan', ''))
    ttype  = data.get('transactionType', '')
    fee    = data.get('fee', '')
    YPW    = F_YELL_W - F_PAD * 2

    slogan_sz = 8
    if slogan:
        for sz in range(28, 6, -1):
            if txt_width(slogan, sz, bold=True) <= YPW and sz <= FOOTER_H * 0.72:
                slogan_sz = sz; break
        draw_bold(c, slogan, F_YELL_X + F_PAD, FY_TOP - slogan_sz - F_PAD, slogan_sz, color=C_NAVYDK)

    bot_parts = list(filter(None, [
        f'【取引態様】{ttype}' if ttype else '',
        f'【手数料】{fee}'     if fee   else '',
    ]))
    if bot_parts:
        bot_line = '　　'.join(bot_parts)
        bot_sz = 7
        for sz in range(16, 6, -1):
            if txt_width(bot_line, sz, bold=True) <= YPW:
                bot_sz = sz; break
        draw_bold(c, bot_line, F_YELL_X + F_PAD, FOOTER_Y + F_PAD, bot_sz, color=C_NAVYDK)

    c.save()


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
