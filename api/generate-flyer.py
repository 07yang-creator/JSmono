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

# ── Text helpers ──────────────────────────────────────────────────────────────
def is_latin(ch): return ord(ch) <= 0x00FF

def txt_width(s, size, bold=False):
    return sum(pdfmetrics.stringWidth(ch,
               (LA_BOLD if bold else LA_FONT) if is_latin(ch) else JP_FONT,
               size) for ch in s)

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

def autosize(s, max_w, max_sz, min_sz=6, bold=False):
    """Return the largest font size ≤ max_sz where text fits in max_w."""
    for sz in range(max_sz, min_sz - 1, -1):
        if txt_width(s, sz, bold) <= max_w: return sz
    return min_sz

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
C_RED    = colors.HexColor('#dc2626')
C_AMBER  = colors.HexColor('#f9d87a')
C_REDBG  = colors.HexColor('#fef2f2')
C_REDBDR = colors.HexColor('#f87171')

# ── Drawing primitives ────────────────────────────────────────────────────────
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

def photo_placeholder(c, x, y, w, h, label, sublabel=''):
    rect(c, x, y, w, h, fill=colors.HexColor('#c8d4e8'), stroke=C_DIV, lw=0.5)
    cx = x + w / 2
    draw_text(c, label,    cx, y + h/2 + 6,  12, color=colors.HexColor('#7a8faa'), align='center')
    if sublabel:
        draw_text(c, sublabel, cx, y + h/2 - 9, 7.5, color=colors.HexColor('#7a8faa'), align='center')

def draw_photo(c, x, y, w, h, b64_data, label, sublabel=''):
    if b64_data:
        try:
            raw = b64_data.split(',', 1)[-1] if ',' in b64_data else b64_data
            img = ImageReader(io.BytesIO(base64.b64decode(raw)))
            iw, ih = img.getSize()
            scale = min(w / iw, h / ih)
            dw, dh = iw * scale, ih * scale
            c.saveState()
            cp = c.beginPath(); cp.rect(x, y, w, h); c.clipPath(cp, stroke=0)
            c.drawImage(img, x + (w-dw)/2, y + (h-dh)/2, dw, dh,
                        preserveAspectRatio=True, mask='auto')
            c.restoreState(); return
        except Exception: pass
    photo_placeholder(c, x, y, w, h, label, sublabel)

def _img_ar(b64_data, default=4/3):
    if b64_data:
        try:
            raw = b64_data.split(',', 1)[-1] if ',' in b64_data else b64_data
            img = ImageReader(io.BytesIO(base64.b64decode(raw)))
            iw, ih = img.getSize()
            return iw / ih if ih else default
        except Exception: pass
    return default

def draw_flex_grid(c, images, x, y, w, h):
    """Aspect-ratio-aware photo grid with white gaps (shadow/mat effect)."""
    GAP = 3
    n = len(images)
    if n == 0: return
    ars = [_img_ar(b) for b, _, _ in images]

    def row(imgs, ars_r, rx, ry, rw, rh):
        ni = len(imgs); usable = rw - GAP * (ni - 1)
        total = sum(ars_r) or 1; cur_x = rx
        for i, (img_t, ar) in enumerate(zip(imgs, ars_r)):
            cw = usable * ar / total
            if i == ni - 1: cw = rx + rw - cur_x
            draw_photo(c, cur_x, ry, cw, rh, *img_t)
            cur_x += cw
            if i < ni - 1:
                rect(c, cur_x, ry, GAP, rh, fill=C_WHITE); cur_x += GAP

    if n == 1:
        draw_photo(c, x, y, w, h, *images[0])
    elif n == 2:
        row(images, ars, x, y, w, h)
    elif n == 3:
        rh0 = w / ars[0]; rh1 = w / ((ars[1]+ars[2])/2); tot = rh0+rh1 or 1
        h0 = max(h*.35, min(h*.65, h*rh0/tot)); h1 = h - h0 - GAP
        draw_photo(c, x, y+h1+GAP, w, h0, *images[0])
        rect(c, x, y+h1, w, GAP, fill=C_WHITE)
        row(images[1:], ars[1:], x, y, w, h1)
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
    LCW  = IW * 0.34 * 0.85 * 0.85  # left data column  (≈24.5% of IW)
    RW   = IW - LCW
    LX   = MX
    RX   = LX + LCW
    HALF = RW / 2
    RX1  = RX
    RX2  = RX + HALF

    # ── Vertical — footer first, then content above ───────────────────────────
    FOOTER_H = 34 * mm               # FIXED footer height (27mm + 25%)
    FOOTER_Y = MY                    # footer bottom sits at bottom margin

    CTOP      = H - MY               # content top edge
    CBOT      = MY + FOOTER_H + 2*mm # content bottom edge (2mm gap above footer)
    CONTENT_H = CTOP - CBOT

    TOP_H    = CONTENT_H * 0.48      # top photo band height
    BAND_BOT = CTOP - TOP_H          # bottom of top band = top of mid section
    MID_BOT  = CBOT
    MID_TOP  = BAND_BOT
    MID_H    = MID_TOP - MID_BOT

    # ── Left column top-band zones (all FIXED, sum = TOP_H) ──────────────────
    PRICE_H = 20 * mm                # price strip  (bottom of left top-band)
    ST_H    = 14 * mm                # station strip (middle)
    NAV_H   = TOP_H - PRICE_H - ST_H # navy box     (top, remainder)

    # Navy box bottom y-coordinate
    nav_y   = BAND_BOT + PRICE_H + ST_H

    # Navy box internal equal-thirds zones (bottom → top in y-coords):
    NAV_ROW = NAV_H / 3
    Z1_BOT  = nav_y              ; Z1_TOP = nav_y +   NAV_ROW   # address
    Z2_BOT  = Z1_TOP             ; Z2_TOP = Z1_TOP +  NAV_ROW   # type pill
    Z3_BOT  = Z2_TOP             ; Z3_TOP = Z2_TOP +  NAV_ROW   # property name

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT COLUMN — TOP BAND
    # ══════════════════════════════════════════════════════════════════════════

    # ── Navy box background ───────────────────────────────────────────────────
    rect(c, LX, nav_y, LCW, NAV_H, fill=C_NAVY)

    prop_type = data.get('propertyType', '中古戸建')
    prop_name = data.get('propertyName', '')
    addr_raw  = data.get('address', '')
    short     = addr_raw.replace('東京都','').replace('大阪府','').replace('神奈川県','')[:22]

    # Zone 3 (top third): property name headline
    if prop_name:
        pname_sz = autosize(prop_name, LCW - 10, 18, min_sz=7, bold=True)
        pname_y  = Z3_BOT + (NAV_ROW - pname_sz) / 2   # vertically centered baseline
        draw_bold(c, prop_name, LX + LCW/2, pname_y, pname_sz,
                  color=C_WHITE, align='center')
        hline(c, LX + 4, LX + LCW - 4, Z3_BOT, color=C_AMBER, lw=0.7)

    # Zone 2 (middle third): type pill, centered in zone
    pill_pad_x, pill_pad_y = 8, 4
    bw      = txt_width(prop_type, PILL_SZ) + pill_pad_x * 2
    bh      = PILL_SZ + pill_pad_y * 2
    pill_x  = LX + (LCW - bw) / 2
    pill_y  = Z2_BOT + (NAV_ROW - bh) / 2
    rect(c, pill_x, pill_y, bw, bh, fill=C_ACCENT)
    draw_text(c, prop_type, pill_x + pill_pad_x, pill_y + pill_pad_y,
              PILL_SZ, color=C_WHITE)
    hline(c, LX + 4, LX + LCW - 4, Z2_BOT, color=colors.HexColor('#2a5cbf'), lw=0.4)

    # Zone 1 (bottom third): address, centered in zone
    addr_sz = autosize(short, LCW - 10, 14, min_sz=6, bold=True)
    addr_y  = Z1_BOT + (NAV_ROW - addr_sz) / 2
    draw_bold(c, short, LX + LCW/2, addr_y, addr_sz, color=C_WHITE, align='center')

    # ── Station strip (fixed height ST_H = 14mm) ──────────────────────────────
    rect(c, LX, BAND_BOT + PRICE_H, LCW, ST_H,
         fill=colors.HexColor('#dce8f8'))
    stations = data.get('stations', [])[:3]
    # 3 lines fit: each takes (ST_FONT + line_gap). Distribute evenly in ST_H.
    n_st     = max(len(stations), 1)
    st_line_h = ST_H / n_st
    for i, st in enumerate(stations):
        ln    = st.get('line', '')
        stn   = st.get('station', '').replace('駅', '')
        wk    = st.get('walk', '')
        line_t = truncate_text(f"{ln}　{stn}駅 徒歩{wk}分", LCW - 10, ST_FONT)
        # Baseline: centered within its slice
        st_y  = BAND_BOT + PRICE_H + ST_H - (i + 0.5) * st_line_h - ST_FONT * 0.3
        draw_text(c, line_t, LX + LCW/2, st_y, ST_FONT, color=C_NAVY, align='center')

    # ── Price strip (fixed height PRICE_H = 20mm) ────────────────────────────
    rect(c, LX, BAND_BOT, LCW, PRICE_H, fill=C_LBLUE)

    price_raw = data.get('price', '')
    num_part  = price_raw.replace('万円', '').strip()
    tax_lbl   = '万円（税込）' if '税込' in data.get('taxIncluded', '税込') else '万円（税別）'
    tax_sz    = ST_FONT

    price_sz  = autosize(num_part, LCW - txt_width(tax_lbl, tax_sz, True) - 14,
                         int(PRICE_H * 0.80), min_sz=9, bold=True)
    combo_w   = txt_width(num_part, price_sz, bold=True) + txt_width(tax_lbl, tax_sz, bold=True) + 4
    price_x   = LX + (LCW - combo_w) / 2
    price_y   = BAND_BOT + (PRICE_H - price_sz) / 2
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

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PHOTO AREA
    # ══════════════════════════════════════════════════════════════════════════
    if variant == 'B':
        draw_flex_grid(c, [
            (data.get('k1Image',''), '外　観',      '（K1）'),
            (data.get('k2Image',''), '外観写真２',  '（K2）'),
            (data.get('k3Image',''), '外観写真３',  '（K3）'),
            (data.get('k4Image',''), '間取り / 地図','（K4）'),
        ], RX, MID_BOT, RW, CONTENT_H)

    rect(c, RX, MID_BOT, RW, CONTENT_H, fill=None, stroke=C_DIV, lw=0.5)

    lease    = data.get('leasePeriod', '')
    grent    = data.get('groundRent', '')
    status   = data.get('currentStatus', '')
    handover = data.get('handover', '')

    if variant != 'B':
        # Q1-top: K1 exterior photo
        draw_photo(c, RX1, BAND_BOT, HALF, TOP_H,
                   data.get('k1Image',''), '外　観', '（写真をここに挿入）')
        # Q2-top: K5 map
        draw_photo(c, RX2, BAND_BOT, HALF, TOP_H,
                   data.get('k5Image',''), '地　図', '（地図を挿入）')

    if variant != 'B':
        # Q1-bottom: H/I 周辺環境・学区 info box
        rect(c, RX1, MID_BOT, HALF, MID_H,
             fill=colors.HexColor('#f0f5ff'), stroke=C_DIV, lw=0.5)

        q2y    = MID_BOT + MID_H - 4
        qpad   = 4
        qiw    = HALF - qpad * 2

        # G — 借地条件
        if lease or grent:
            if q2y - 11 >= MID_BOT:
                q2y -= 11
                rect(c, RX1, q2y, HALF, 11, fill=C_NAVY)
                draw_bold(c, '借地条件', RX1+qpad, q2y+3, 6.5, color=C_WHITE)
            if grent and q2y - 10 >= MID_BOT:
                q2y -= 10
                draw_text(c, f'地代　{grent}', RX1+qpad, q2y+2, 6.5, color=C_BLACK)
            if lease and q2y - 9 >= MID_BOT:
                q2y -= 9
                draw_text(c, truncate_text(lease, qiw, 6.5), RX1+qpad, q2y+2, 6.5, color=C_BLACK)
            if (status or handover) and q2y - 10 >= MID_BOT:
                q2y -= 2
                rect(c, RX1, q2y-10, HALF, 10, fill=C_MBLUE)
                draw_text(c, f'現況:{status}　引渡:{handover}', RX1+qpad, q2y-7, 6, color=C_NAVY)
                q2y -= 12
            q2y -= 4

        # H — 周辺環境 (flowing text)
        nearby = data.get('nearby', [])
        if nearby and q2y - 11 >= MID_BOT:
            q2y -= 11
            rect(c, RX1, q2y, HALF, 11, fill=C_NAVY)
            draw_bold(c, '■ 周辺環境', RX1+qpad, q2y+3, 6.5, color=C_WHITE)

        if nearby:
            nb_sz   = 7; line_h = nb_sz + 3; SEP = '　・　'
            avail_w = HALF - qpad * 2
            parts   = [f"{nb.get('name','')}({nb.get('walk','')})"
                       for nb in nearby if nb.get('name')]
            nb_lines = []; cur = ''
            for p in parts:
                chunk = (SEP if cur else '') + p
                if cur and txt_width(cur+chunk, nb_sz) > avail_w:
                    nb_lines.append(cur); cur = p
                else: cur += chunk
            if cur: nb_lines.append(cur)
            for line in nb_lines[:5]:
                if q2y - line_h < MID_BOT: break
                q2y -= line_h
                draw_text(c, line, RX1+qpad, q2y+2, nb_sz, color=C_BLACK)

        # I — 学区
        school_lines = []
        if data.get('elemSchool'):
            school_lines.append(('小', data['elemSchool'], data.get('elemSchoolDist','')))
        if data.get('juniorSchool'):
            school_lines.append(('中', data['juniorSchool'], data.get('juniorSchoolDist','')))
        if school_lines and q2y - 11 >= MID_BOT:
            q2y -= 15
            rect(c, RX1, q2y, HALF, 11, fill=C_NAVY)
            draw_bold(c, '■ 学区', RX1+qpad, q2y+3, 6.5, color=C_WHITE)
        for i, (tag, nm, dist) in enumerate(school_lines):
            if q2y - 10 < MID_BOT: break
            q2y -= 10
            bg = C_LBLUE if i % 2 else C_WHITE
            rect(c, RX1, q2y, HALF, 10, fill=bg, stroke=C_DIV, lw=0.2)
            draw_text(c, truncate_text(f'{tag}:  {nm}', qiw*.62, 6.5),
                      RX1+qpad, q2y+2, 6.5, color=C_BLACK)
            draw_text(c, dist, RX1+HALF-qpad, q2y+2, 6, color=C_MUTED, align='right')

    # ── Promo ribbon (auto-scale) ─────────────────────────────────────────────
    promo = data.get('specialPromo', '').strip()
    if promo:
        cx_r = W - MX; cy_t = CTOP
        rsz  = 7.5
        ptw  = txt_width(promo, rsz, bold=True)
        a    = max(55, int(ptw / math.sqrt(2)) + 20)
        bw2  = max(28, int(a * 0.55))
        P1   = (cx_r-a, cy_t); P2 = (cx_r-a+bw2, cy_t)
        P3   = (cx_r, cy_t-a+bw2); P4 = (cx_r, cy_t-a)
        c.saveState()
        cl = c.beginPath(); cl.rect(RX, CBOT, RW, CONTENT_H); c.clipPath(cl, stroke=0)
        c.setFillColor(colors.HexColor('#c0000066'))
        sh = c.beginPath()
        sh.moveTo(P1[0]+2,P1[1]-2); sh.lineTo(P2[0]+2,P2[1]-2)
        sh.lineTo(P3[0]+2,P3[1]-2); sh.lineTo(P4[0]+2,P4[1]-2)
        sh.close(); c.drawPath(sh, fill=1, stroke=0)
        c.setFillColor(C_RED)
        pr = c.beginPath()
        pr.moveTo(*P1); pr.lineTo(*P2); pr.lineTo(*P3); pr.lineTo(*P4)
        pr.close(); c.drawPath(pr, fill=1, stroke=0)
        c.setStrokeColor(C_AMBER); c.setLineWidth(0.8)
        c.line(*P1,*P4); c.line(*P2,*P3)
        mid_x = (P1[0]+P3[0])/2; mid_y = (P1[1]+P3[1])/2
        c.translate(mid_x, mid_y); c.rotate(-45)
        c.setFillColor(C_WHITE)
        _draw_rotated_text(c, promo, -ptw/2, -rsz/2, rsz)
        c.restoreState()

    # ── Grid dividers (Variant A only) ────────────────────────────────────────
    vline(c, RX, CBOT, CTOP, color=C_DIV, lw=0.8)
    if variant != 'B':
        vline(c, RX2, CBOT, CTOP, color=C_DIV, lw=0.5)
        hline(c, RX, W-MX, BAND_BOT, color=C_DIV, lw=0.6)

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT COLUMN — MIDDLE SECTION (property data rows)
    # ══════════════════════════════════════════════════════════════════════════
    rect(c, LX, MID_BOT, LCW, MID_H, fill=C_WHITE)

    LLBW = LCW * 0.34
    LVBW = LCW - LLBW
    LRH  = 13
    LBAR = 12
    ly   = MID_TOP

    def lsec(title):
        nonlocal ly
        if ly - LBAR < MID_BOT: return
        ly -= LBAR
        rect(c, LX, ly, LCW, LBAR, fill=C_NAVY)
        draw_bold(c, title, LX+4, ly+3, 7, color=C_WHITE)

    def lrow(lbl, val, alt=False):
        nonlocal ly
        if not val: return
        if ly - LRH < MID_BOT: return
        ly -= LRH
        bg = C_LBLUE if alt else C_WHITE
        rect(c, LX,        ly, LLBW, LRH, fill=C_SECBG, stroke=C_DIV, lw=0.3)
        draw_text(c, lbl,  LX+2, ly+3, 6.5, color=C_NAVY)
        rect(c, LX+LLBW,   ly, LVBW, LRH, fill=bg, stroke=C_DIV, lw=0.3)
        draw_text(c, truncate_text(val, LVBW-5, 6.5), LX+LLBW+3, ly+3, 6.5, color=C_BLACK)

    # 所在地
    lsec('■ 所在地')
    lrow('所在地', addr_raw)

    # 物件概要
    lsec('■ 物件概要')
    la = f"{data.get('landArea','')}㎡"
    if data.get('landAreaTsubo'): la += f"  ({data['landAreaTsubo']}坪)"
    fa_parts = [data.get(f'floorArea{i}','') for i in range(1,5)]
    fa = '  '.join(x for x in fa_parts if x)
    tf = f"{data.get('totalFloorArea','')}㎡" if data.get('totalFloorArea') else ''

    lrow('土地面積', la)
    lrow('土地権利', data.get('landRight',''),     alt=True)
    lrow('地目',     data.get('landCategory',''))
    lrow('接面道路', data.get('frontRoad',''),      alt=True)
    lrow('再建築',   rebuild)
    lrow('築年月',   data.get('builtYear',''),      alt=True)
    lrow('構造',     data.get('structure',''))
    lrow('床面積',   fa,                            alt=True)
    if tf: lrow('合計床面積', tf)
    lrow('間取り',   data.get('layout',''),         alt=True)
    lrow('現況',     status)
    lrow('引渡し',   handover,                      alt=True)

    # マンション専用
    if data.get('propertyType','') == 'マンション':
        lsec('■ マンション情報')
        lrow('建物名',    data.get('buildingName',''))
        lrow('所在階',    data.get('floorInfo',''),    alt=True)
        ea = f"{data.get('exclusiveArea','')}㎡" if data.get('exclusiveArea') else ''
        ba = f"{data.get('balconyArea','')}㎡"  if data.get('balconyArea')   else ''
        lrow('専有面積',  ea)
        lrow('バルコニー',ba,                          alt=True)
        mf = f"{data.get('managementFee','')}円/月" if data.get('managementFee') else ''
        rf = f"{data.get('repairFund','')}円/月"    if data.get('repairFund')    else ''
        lrow('管理費',    mf)
        lrow('修繕積立',  rf,                          alt=True)
        lrow('管理会社',  data.get('managementCo',''))
        lrow('管理形態',  data.get('managementType',''),alt=True)

    # 法令制限
    if data.get('propertyType','') != 'マンション':
        lsec('■ 法令制限')
        lrow('都市計画', data.get('cityPlan',''))
        lrow('用途地域', data.get('useZone',''),        alt=True)
        lrow('防火指定', data.get('fireZone',''))
        lrow('建ぺい率', data.get('bcr',''),            alt=True)
        lrow('容積率',   data.get('far',''))
        lrow('高度地区', data.get('heightDistrict',''), alt=True)
        if data.get('otherLegal'):
            lrow('その他', data['otherLegal'])

    # ライフライン
    up = []
    if data.get('electric'): up.append(f"電気：{data['electric']}")
    if data.get('gas'):      up.append(f"ガス：{data['gas']}")
    if data.get('water'):    up.append(f"水道：{data['water']}")
    if up:
        lsec('■ ライフライン')
        if ly - LRH >= MID_BOT:
            ly -= LRH
            rect(c, LX, ly, LCW, LRH, fill=C_WHITE, stroke=C_DIV, lw=0.3)
            draw_text(c, truncate_text('　'.join(up), LCW-6, 6.5),
                      LX+3, ly+3, 6.5, color=C_BLACK)

    # 備考
    DISC = '現況と図面が相違する場合は現況を優先します'
    remarks = [r.strip() for r in data.get('remarks','').split('\n')
               if r.strip() and DISC not in r]
    if remarks:
        lsec('■ 備考')
        for i, r in enumerate(remarks):
            lrow('', r, alt=(i%2==1))

    if MID_BOT + 8 < ly:
        draw_text(c, '※現況と図面が相違する場合は現況を優先します。',
                  LX+2, MID_BOT+4, 5.5, color=C_MUTED)

    # Q2-bottom: K2 floor plan (Variant A)
    if variant != 'B':
        draw_photo(c, RX2, MID_BOT, HALF, MID_H,
                   data.get('k2Image',''), '間取り図', '（間取り図を挿入）')

    # ══════════════════════════════════════════════════════════════════════════
    # FOOTER — FIXED 34mm, IW width, left→right: Logo|Name|Info|Contact|Yellow
    # ══════════════════════════════════════════════════════════════════════════
    F_PAD   = 5
    FY_TOP  = FOOTER_Y + FOOTER_H
    DIVC    = colors.HexColor('#2a4a8a')

    # Fixed section widths (sum = IW)
    F_LOGO_W = FOOTER_H              # square logo
    F_NAME_W = IW * 0.15
    F_INFO_W = IW * 0.24
    F_CONT_W = IW * 0.23
    F_YELL_W = IW - F_LOGO_W - F_NAME_W - F_INFO_W - F_CONT_W

    # Left-edge x of each section
    F_LOGO_X = MX
    F_NAME_X = F_LOGO_X + F_LOGO_W
    F_INFO_X = F_NAME_X + F_NAME_W
    F_CONT_X = F_INFO_X + F_INFO_W
    F_YELL_X = F_CONT_X + F_CONT_W

    # Navy background (full IW width)
    rect(c, MX, FOOTER_Y, IW, FOOTER_H, fill=C_NAVYDK)

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

    vline(c, F_NAME_X, FOOTER_Y, FY_TOP, color=DIVC, lw=0.6)

    # ── b) Company name ───────────────────────────────────────────────────────
    brand = data.get('brandName', '')
    co    = data.get('companyName', '')
    longest = max((brand, co), key=len) if (brand or co) else ''
    name_sz = autosize(longest, F_NAME_W - F_PAD*2, 20, min_sz=7, bold=True)
    ny = FY_TOP - F_PAD
    if brand:
        draw_bold(c, brand, F_NAME_X+F_PAD, ny, name_sz, color=C_WHITE)
        ny -= name_sz + 3
    if co and co != brand:
        draw_bold(c, co, F_NAME_X+F_PAD, ny, max(name_sz-3, 7), color=C_WHITE)

    vline(c, F_INFO_X, FOOTER_Y, FY_TOP, color=DIVC, lw=0.6)

    # ── c) Company info ───────────────────────────────────────────────────────
    ISZ       = 6.5
    addr_co   = data.get('companyAddress', '')
    tel       = data.get('tel', '')
    fax       = data.get('fax', '')
    em        = data.get('email', '')
    dept      = data.get('department', '')
    licenseNo = data.get('licenseNo', '')
    assoc     = data.get('association', '')
    iy = FY_TOP - F_PAD
    def irow(txt, col, sz=ISZ):
        nonlocal iy
        if not txt or iy - sz < FOOTER_Y: return
        draw_text(c, truncate_text(txt, F_INFO_W-F_PAD*2, sz),
                  F_INFO_X+F_PAD, iy, sz, color=col)
        iy -= sz + 2.5
    irow(dept,      colors.HexColor('#aabbd4'))
    irow(addr_co,   C_STEELBL)
    irow(f'TEL：{tel}' if tel else '', C_STEELBL)
    irow(f'FAX：{fax}' if fax else '', C_STEELBL)
    irow(f'✉ {em}'    if em  else '', C_STEELBL)
    irow(licenseNo, colors.HexColor('#8aa8cc'), sz=ISZ-0.5)
    irow(assoc,     colors.HexColor('#8aa8cc'), sz=ISZ-1)

    vline(c, F_CONT_X, FOOTER_Y, FY_TOP, color=DIVC, lw=0.6)

    # ── d) Contact ────────────────────────────────────────────────────────────
    OBC_H = int(FOOTER_H * 0.16)    # orange strip ≈16% of footer height
    rect(c, F_CONT_X, FY_TOP-OBC_H, F_CONT_W, OBC_H, fill=C_ACCENT)
    draw_bold(c, 'お問い合わせ先',
              F_CONT_X+F_CONT_W/2, FY_TOP-OBC_H+3, 9, color=C_WHITE, align='center')

    ag     = data.get('agentName', '')
    ag_tel = data.get('agentTel', '')
    CW     = F_CONT_W - F_PAD*2
    cy2    = FY_TOP - OBC_H - 4
    if ag:
        asz = autosize(f'【担当】{ag}', CW, min(name_sz, 15), min_sz=7, bold=True)
        draw_bold(c, f'【担当】{ag}', F_CONT_X+F_PAD, cy2, asz, color=C_WHITE)
        cy2 -= asz + 3
    tel_str = ag_tel or tel
    if tel_str:
        tsz = autosize(f'TEL：{tel_str}', CW, min(name_sz, 16), min_sz=7, bold=True)
        draw_bold(c, f'TEL：{tel_str}', F_CONT_X+F_PAD, cy2, tsz, color=C_WHITE)

    vline(c, F_YELL_X, FOOTER_Y, FY_TOP, color=DIVC, lw=0.6)

    # ── e) Yellow slogan area (rightmost) ─────────────────────────────────────
    rect(c, F_YELL_X, FOOTER_Y, F_YELL_W, FOOTER_H,
         fill=colors.HexColor('#f5c800'))

    slogan = data.get('catchcopy', data.get('companySlogan', ''))
    ttype  = data.get('transactionType', '')
    fee    = data.get('fee', '')
    YPW    = F_YELL_W - F_PAD*2

    # Slogan in top ~65% of yellow area
    yell_top_zone = FOOTER_H * 0.65
    if slogan:
        ssz = autosize(slogan, YPW, int(yell_top_zone * 0.7), min_sz=6, bold=True)
        sy  = FY_TOP - ssz - F_PAD
        draw_bold(c, slogan, F_YELL_X+F_PAD, sy, ssz, color=C_NAVYDK)

    # 取引態様 / 手数料 on one line in bottom ~35%
    bot_parts = list(filter(None, [
        f'【取引態様】{ttype}' if ttype else '',
        f'【手数料】{fee}'     if fee   else '',
    ]))
    if bot_parts:
        bot_line = '　　'.join(bot_parts)
        bsz = autosize(bot_line, YPW, 14, min_sz=6, bold=True)
        draw_bold(c, bot_line, F_YELL_X+F_PAD, FOOTER_Y+F_PAD, bsz, color=C_NAVYDK)

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
