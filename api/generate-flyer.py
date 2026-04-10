"""
generate_flyer.py  —  Justsalemono  (Template 1)
─────────────────────────────────────────────────────────────
A4 portrait.  Three columns, four cells in the right area:

  LEFT (38%)  │  Q1 (31%)        │  Q2 (31%)
  ────────────┼──────────────────┼──────────────────
  TOP BAND    │  K1 外観写真      │  H/I 周辺環境    ← Variant A
  (title/     │                  │  or K2 photo     ← Variant B
   price)     │                  │  [promo flag ▶]
  ────────────┼──────────────────┼──────────────────
  data rows   │  K5 地図         │  K2/K4 間取り図   ← Variant A
              │                  │  K3/K4 photo     ← Variant B
  ────────────┴──────────────────┴──────────────────
  FOOTER  (full width — company info)

Column boundaries are IDENTICAL for top and bottom sections
→ clean visual grid, no mid-page column shift.

ly convention: ly = current TOP-EDGE; helpers decrement BEFORE drawing.
"""

import json, sys, os, io, math, base64
from reportlab.lib.pagesizes import A4, portrait, landscape
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
    images: list of (b64, label, sublabel) tuples.
    Images are distributed into rows; within each row widths scale
    proportionally to each image's aspect ratio.
    """
    n = len(images)
    if n == 0:
        return
    ars = [_img_ar(b) for b, _, _ in images]

    def row(imgs, ars_r, rx, ry, rw, rh):
        """Draw one row of images side-by-side."""
        total = sum(ars_r) or 1
        cur_x = rx
        for i, (img_tuple, ar) in enumerate(zip(imgs, ars_r)):
            cell_w = rw * ar / total
            if i == len(imgs) - 1:          # last cell takes remaining width
                cell_w = rx + rw - cur_x
            draw_photo(c, cur_x, ry, cell_w, rh, *img_tuple)
            # thin divider line between cells
            if i < len(imgs) - 1:
                vline(c, cur_x + cell_w, ry, ry + rh, color=C_DIV, lw=0.5)
            cur_x += cell_w

    if n == 1:
        draw_photo(c, x, y, w, h, *images[0])

    elif n == 2:
        # Two images side by side, single row
        row(images, ars, x, y, w, h)

    elif n == 3:
        # Top row: image 0 full-width; bottom row: images 1 & 2 side-by-side
        # Row heights weighted by effective height at full width
        rh0_nat = w / ars[0]
        rh1_nat = w / ((ars[1] + ars[2]) / 2)
        tot = rh0_nat + rh1_nat or 1
        rh0 = max(h * 0.35, min(h * 0.65, h * rh0_nat / tot))
        rh1 = h - rh0
        draw_photo(c, x, y + rh1, w, rh0, *images[0])
        hline(c, x, x + w, y + rh1, color=C_DIV, lw=0.5)
        row(images[1:], ars[1:], x, y, w, rh1)

    else:  # n == 4
        # Two rows of two images each; row height weighted by avg aspect ratio
        avg_top = (ars[0] + ars[1]) / 2
        avg_bot = (ars[2] + ars[3]) / 2
        rh_top_nat = w / avg_top
        rh_bot_nat = w / avg_bot
        tot = rh_top_nat + rh_bot_nat or 1
        rh_top = max(h * 0.35, min(h * 0.65, h * rh_top_nat / tot))
        rh_bot = h - rh_top
        row(images[:2], ars[:2], x, y + rh_bot, w, rh_top)
        hline(c, x, x + w, y + rh_bot, color=C_DIV, lw=0.5)
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

    # ── Column geometry  (consistent top-to-bottom) ───────────────────────────
    LCW  = IW * 0.34             # left data column  (34%)
    RW   = IW - LCW              # right photo area  (66%)
    LX   = MX                    # left column left edge
    RX   = LX + LCW              # right area left edge

    # Within the right area: two equal columns
    HALF = RW / 2
    RX1  = RX                    # Q1 left edge
    RX2  = RX + HALF             # Q2 left edge

    # ── Vertical anchors ──────────────────────────────────────────────────────
    STRIP_H   = 5.5 * mm         # bottom licence strip
    FOOTER_H  = 18   * mm        # footer band above strip
    STRIP_Y   = MY
    FOOTER_Y  = MY + STRIP_H

    CTOP      = H - MY           # content top
    CBOT      = MY + STRIP_H + FOOTER_H + 1.5 * mm  # content bottom

    # Right area vertical split: top band (~47%) / middle (~53%)
    CONTENT_H = CTOP - CBOT
    TOP_H     = CONTENT_H * 0.48
    BAND_TOP  = CTOP
    BAND_BOT  = CTOP - TOP_H

    MID_TOP   = BAND_BOT
    MID_BOT   = CBOT
    MID_H     = MID_TOP - MID_BOT

    # ─────────────────────────────────────────────────────────────────────────
    # TOP BAND — LEFT column  (navy header + price strip)
    # ─────────────────────────────────────────────────────────────────────────
    PRICE_H = 20 * mm
    NAV_H   = TOP_H - PRICE_H

    rect(c, LX, BAND_BOT + PRICE_H, LCW, NAV_H, fill=C_NAVY)

    # ── Property type pill ────────────────────────────────────────────────────
    prop_type = data.get('propertyType', '中古戸建')
    PILL_SZ = 10
    pill_pad_x, pill_pad_y = 8, 4
    bw = txt_width(prop_type, PILL_SZ) + pill_pad_x * 2
    bh = PILL_SZ + pill_pad_y * 2
    by = BAND_BOT + PRICE_H + NAV_H - bh - 6  # near top of navy box
    rect(c, LX + 5, by, bw, bh, fill=C_ACCENT)
    draw_text(c, prop_type, LX + 5 + pill_pad_x, by + pill_pad_y, PILL_SZ, color=C_WHITE)

    # ── Address — auto-scaled to fill box width ───────────────────────────────
    addr_raw = data.get('address', '')
    short = addr_raw.replace('東京都','').replace('大阪府','').replace('神奈川県','')
    short = short[:20]
    addr_avail = LCW - 10
    addr_sz = 8
    for sz in range(22, 7, -1):
        if txt_width(short, sz, bold=True) <= addr_avail:
            addr_sz = sz
            break
    addr_y = by - addr_sz - 5
    draw_bold(c, short, LX + 5, addr_y, addr_sz, color=C_WHITE)

    # ── Station lines — auto-scaled ───────────────────────────────────────────
    stations = data.get('stations', [])[:3]
    # Determine font size to fill remaining height
    remain_h = addr_y - (BAND_BOT + PRICE_H + 4)
    st_sz = 7
    if stations:
        st_sz_try = int(remain_h / max(len(stations), 1) * 0.75)
        for sz in range(min(st_sz_try, 14), 6, -1):
            sample = f"{stations[0].get('line','')}  『{stations[0].get('station','').replace('駅','')}』駅 徒歩{stations[0].get('walk','')}分"
            if txt_width(sample, sz) <= addr_avail:
                st_sz = sz
                break
    st_y = addr_y - addr_sz - 6
    for st in stations:
        if st_y - st_sz < BAND_BOT + PRICE_H + 2: break
        ln  = st.get('line', '')
        stn = st.get('station', '').replace('駅', '')
        wk  = st.get('walk', '')
        draw_text(c, f"{ln}  『{stn}』駅 徒歩{wk}分",
                  LX + 5, st_y, st_sz, color=C_DARKBL)
        st_y -= st_sz + 4

    # ── Price strip — price auto-sized and centred ────────────────────────────
    rect(c, LX, BAND_BOT, LCW, PRICE_H, fill=C_LBLUE)

    price_raw = data.get('price', '')
    num_part  = price_raw.replace('万円', '').strip()
    tax_lbl   = '万円（税込）' if '税込' in data.get('taxIncluded', '税込') else '万円（税別）'

    # Find largest font that fits width & ~80% of height
    price_avail_w = LCW - 10
    price_sz = 10
    for sz in range(48, 9, -1):
        combo_w = txt_width(num_part, sz, bold=True) + txt_width(tax_lbl, max(sz//3, 8), bold=True) + 4
        if combo_w <= price_avail_w and sz <= PRICE_H * 0.82:
            price_sz = sz
            break
    tax_sz   = max(int(price_sz * 0.44), 7)
    # Vertical centre in price box
    price_y  = BAND_BOT + (PRICE_H - price_sz) / 2
    # Horizontal centre
    combo_w  = txt_width(num_part, price_sz, bold=True) + txt_width(tax_lbl, tax_sz, bold=True) + 4
    price_x  = LX + (LCW - combo_w) / 2
    draw_bold(c, num_part, price_x, price_y, price_sz, color=C_ACCENT)
    draw_bold(c, tax_lbl,
              price_x + txt_width(num_part, price_sz, bold=True) + 4,
              price_y + 2, tax_sz, color=C_ACCENT)

    # 販売価格 label — small, top-left of price strip
    draw_text(c, '販売価格', LX + 5, BAND_BOT + PRICE_H - 9, 6, color=C_MUTED)

    rebuild = data.get('rebuild', '')
    if rebuild:
        rbw = txt_width(rebuild, 7) + 10
        rect(c, LX + LCW - rbw - 4, BAND_BOT + PRICE_H - 13, rbw, 11,
             fill=C_REDBG, stroke=C_REDBDR, lw=0.6)
        draw_text(c, rebuild, LX + LCW - rbw/2 - 4, BAND_BOT + PRICE_H - 10, 7,
                  color=C_RED, align='center')

    # ─────────────────────────────────────────────────────────────────────────
    # RIGHT PHOTO AREA
    # Variant B: 4-photo flexible grid fills the entire right area
    # Variant A: Q1-top = K1 photo; Q2-top = H/I info box; bottom = K5 + K2
    # ─────────────────────────────────────────────────────────────────────────
    if variant == 'B':
        b_images = [
            (data.get('k1Image',''), '外　観',    '（K1）'),
            (data.get('k2Image',''), '外観写真２', '（K2）'),
            (data.get('k3Image',''), '外観写真３', '（K3）'),
            (data.get('k4Image',''), '間取り / 地図', '（K4）'),
        ]
        draw_flex_grid(c, b_images, RX, MID_BOT, RW, CONTENT_H)

    # Draw outer border for right area
    rect(c, RX, MID_BOT, RW, CONTENT_H, fill=None, stroke=C_DIV, lw=0.5)

    # ─────────────────────────────────────────────────────────────────────────
    # VARIANT A — TOP BAND — Q1  (K1 外観写真)
    # ─────────────────────────────────────────────────────────────────────────
    lease   = data.get('leasePeriod', '')
    grent   = data.get('groundRent', '')
    status  = data.get('currentStatus', '')
    handover = data.get('handover', '')

    if variant != 'B':
        draw_photo(c, RX1, BAND_BOT, HALF, TOP_H,
                   data.get('k1Image', ''), '外　観', '（写真をここに挿入）')

    if variant == 'B':
        pass  # already drawn above via flex grid
    elif False:  # placeholder to maintain structure
        pass
    else:
        # Q2-top = H/I 周辺環境・学区 info box
        rect(c, RX2, BAND_BOT, HALF, TOP_H,
             fill=colors.HexColor('#f0f5ff'), stroke=C_DIV, lw=0.5)

        q2y = BAND_BOT + TOP_H - 4    # current y (top-of-content, decrements downward)
        q2_pad = 4                     # horizontal padding inside Q2
        q2_inner_w = HALF - q2_pad * 2

        # G box content (借地条件) if applicable
        if lease or grent:
            g_bar_h = 11
            if q2y - g_bar_h >= BAND_BOT:
                q2y -= g_bar_h
                rect(c, RX2, q2y, HALF, g_bar_h, fill=C_NAVY)
                draw_bold(c, '借地条件', RX2 + q2_pad, q2y + 3, 6.5, color=C_WHITE)
            if grent and q2y - 10 >= BAND_BOT:
                q2y -= 10
                draw_text(c, f'地代　{grent}', RX2 + q2_pad, q2y + 2, 6.5, color=C_BLACK)
            if lease and q2y - 9 >= BAND_BOT:
                q2y -= 9
                lt = truncate_text(lease, q2_inner_w, 6.5)
                draw_text(c, lt, RX2 + q2_pad, q2y + 2, 6.5, color=C_BLACK)
            if (status or handover) and q2y - 10 >= BAND_BOT:
                q2y -= 2
                rect(c, RX2, q2y - 10, HALF, 10, fill=C_MBLUE)
                draw_text(c, f'現況:{status}　引渡:{handover}',
                          RX2 + q2_pad, q2y - 7, 6, color=C_NAVY)
                q2y -= 12
            q2y -= 4   # gap before H/I

        # H 周辺環境 section
        nearby = data.get('nearby', [])
        if nearby and q2y - 11 >= BAND_BOT:
            q2y -= 11
            rect(c, RX2, q2y, HALF, 11, fill=C_NAVY)
            draw_bold(c, '■ 周辺環境', RX2 + q2_pad, q2y + 3, 6.5, color=C_WHITE)
        for i, nb in enumerate(nearby[:6]):
            if q2y - 10 < BAND_BOT: break
            q2y -= 10
            bg = C_LBLUE if i % 2 == 1 else C_WHITE
            rect(c, RX2, q2y, HALF, 10, fill=bg, stroke=C_DIV, lw=0.2)
            name_t = truncate_text('・' + nb.get('name',''), q2_inner_w * 0.62, 6.5)
            dist_t = truncate_text(nb.get('walk',''), q2_inner_w * 0.38, 6)
            draw_text(c, name_t, RX2 + q2_pad, q2y + 2, 6.5, color=C_BLACK)
            draw_text(c, dist_t, RX2 + HALF - q2_pad, q2y + 2, 6, color=C_MUTED, align='right')

        # I 学区 section
        school_lines = []
        if data.get('elemSchool'):
            school_lines.append(('小', data['elemSchool'], data.get('elemSchoolDist','')))
        if data.get('juniorSchool'):
            school_lines.append(('中', data['juniorSchool'], data.get('juniorSchoolDist','')))
        if school_lines and q2y - 11 >= BAND_BOT:
            q2y -= 4
            q2y -= 11
            rect(c, RX2, q2y, HALF, 11, fill=C_NAVY)
            draw_bold(c, '■ 学区', RX2 + q2_pad, q2y + 3, 6.5, color=C_WHITE)
        for i, (tag, nm, dist) in enumerate(school_lines):
            if q2y - 10 < BAND_BOT: break
            q2y -= 10
            bg = C_LBLUE if i % 2 == 1 else C_WHITE
            rect(c, RX2, q2y, HALF, 10, fill=bg, stroke=C_DIV, lw=0.2)
            nm_t = truncate_text(f'{tag}:  {nm}', q2_inner_w * 0.62, 6.5)
            draw_text(c, nm_t, RX2 + q2_pad, q2y + 2, 6.5, color=C_BLACK)
            draw_text(c, dist, RX2 + HALF - q2_pad, q2y + 2, 6, color=C_MUTED, align='right')

    # ─────────────────────────────────────────────────────────────────────────
    # SPECIAL PROMO — 绶带 (diagonal corner ribbon) top-right of right area
    # ─────────────────────────────────────────────────────────────────────────
    promo = data.get('specialPromo', '').strip()
    if promo:
        cx_r = W - MX       # right edge of content
        cy_t = CTOP         # top edge of content

        a  = 62   # ribbon reach along each edge from corner
        bw = 36   # band width

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

        # Rotated text centred in ribbon
        mid_x = (P1[0] + P3[0]) / 2
        mid_y = (P1[1] + P3[1]) / 2
        promo_txt = truncate_text(promo, bw * 1.3, 7.5, bold=True)
        c.translate(mid_x, mid_y); c.rotate(-45)
        tw = txt_width(promo_txt, 7.5, bold=True)
        c.setFillColor(C_WHITE)
        _draw_rotated_text(c, promo_txt, -tw/2, -3.75, 7.5)
        c.restoreState()

    # ─────────────────────────────────────────────────────────────────────────
    # GRID DIVIDERS (Variant A only — Variant B dividers drawn by flex grid)
    # ─────────────────────────────────────────────────────────────────────────
    vline(c, RX, CBOT, CTOP, color=C_DIV, lw=0.8)   # left|right column divider
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

    # 所在地
    lsec('■ 所在地')
    lrow('所在地', addr_raw)

    # 物件概要
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

    # マンション専用 (E)
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

    # 法令制限 (F) — skip for マンション
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

    # ライフライン (J1)
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

    # 備考 (J5)
    DISCLAIMER = '現況と図面が相違する場合は現況を優先します'
    remarks = [r.strip() for r in data.get('remarks','').split('\n')
               if r.strip() and DISCLAIMER not in r]
    if remarks:
        lsec('■ 備考')
        for i, r in enumerate(remarks):
            lrow('', r, alt=(i % 2 == 1))

    # Disclaimer text at bottom
    if MID_BOT + 8 < ly:
        draw_text(c, '※現況と図面が相違する場合は現況を優先します。',
                  LX + 2, MID_BOT + 4, 5.5, color=C_MUTED)

    # ─────────────────────────────────────────────────────────────────────────
    # MIDDLE SECTION — Q1 bottom  (K5 地図)
    # ─────────────────────────────────────────────────────────────────────────
    # Variant B photos already drawn via draw_flex_grid above
    if variant != 'B':
        draw_photo(c, RX1, MID_BOT, HALF, MID_H,
                   data.get('k5Image', ''), '地　図', '（地図を挿入）')
        draw_photo(c, RX2, MID_BOT, HALF, MID_H,
                   data.get('k2Image', ''), '間取り図', '（間取り図を挿入）')

    # ─────────────────────────────────────────────────────────────────────────
    # FOOTER  — replicates sample layout:
    #   [LOGO | Brand/Company/Address] | [Dept + お問い合わせ先 + TEL/FAX/Mail] | [YELLOW: Slogan + 担当/取引態様/手数料]
    #   ───────────────────── bottom strip: licence numbers ─────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    lic   = data.get('licenseNo', '')
    assoc = data.get('association', '')

    # ── Bottom licence strip ──────────────────────────────────────────────────
    rect(c, 0, STRIP_Y, W, STRIP_H, fill=colors.HexColor('#0e2660'))
    strip_parts = list(filter(None, [lic, assoc]))
    if strip_parts:
        draw_text(c, '　■　'.join(strip_parts), MX, STRIP_Y + 1.5, 5, color=C_STEELBL)

    # ── Footer band (full width, navy) ────────────────────────────────────────
    rect(c, 0, FOOTER_Y, W, FOOTER_H, fill=C_NAVYDK)

    # Column widths within footer
    F_LEFT_W   = W * 0.36    # logo + company info
    F_MID_W    = W * 0.38    # department + contact
    F_RIGHT_W  = W - F_LEFT_W - F_MID_W   # yellow slogan column
    F_LEFT_X   = 0
    F_MID_X    = F_LEFT_W
    F_RIGHT_X  = F_LEFT_W + F_MID_W

    FY_TOP  = FOOTER_Y + FOOTER_H   # top of footer band
    F_PAD   = 5

    # ── LEFT section: logo (left) + brand/company/address (right of logo) ────
    logo_b64 = data.get('logoImage', '')
    logo_area_w = F_LEFT_W * 0.32   # reserve left 32% for logo
    text_x = F_LEFT_X + logo_area_w + F_PAD

    if logo_b64:
        try:
            raw = logo_b64.split(',', 1)[-1] if ',' in logo_b64 else logo_b64
            logo_img = ImageReader(io.BytesIO(base64.b64decode(raw)))
            lg_h = FOOTER_H - 6
            lw2, lh2 = logo_img.getSize()
            lg_w = lg_h * lw2 / lh2 if lh2 else lg_h
            lg_w = min(lg_w, logo_area_w - 4)
            c.drawImage(logo_img, F_LEFT_X + (logo_area_w - lg_w) / 2,
                        FOOTER_Y + 3, lg_w, lg_h,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            text_x = F_LEFT_X + F_PAD  # no logo: text starts at left edge
    else:
        text_x = F_LEFT_X + F_PAD

    # Brand + company — auto-scale to fill available width
    brand = data.get('brandName', '')
    co    = data.get('companyName', '')
    text_avail = F_MID_X - text_x - F_PAD
    # Find largest font size that fits for the longest of brand/company
    longest = max((brand, co), key=len) if brand or co else ''
    brand_sz = 8
    for sz in range(20, 7, -1):
        if txt_width(longest, sz, bold=True) <= text_avail:
            brand_sz = sz
            break
    fy = FY_TOP - 5
    if brand:
        draw_bold(c, brand, text_x, fy, brand_sz, color=C_WHITE); fy -= brand_sz + 3
    if co and co != brand:
        draw_bold(c, co, text_x, fy, max(brand_sz - 2, 7), color=C_WHITE); fy -= brand_sz
    addr_co = data.get('companyAddress', '')
    if addr_co:
        draw_text(c, addr_co, text_x, fy, 6, color=C_STEELBL); fy -= 8
    fax = data.get('fax', '')
    if fax:
        draw_text(c, f'FAX：{fax}', text_x, fy, 6, color=C_STEELBL)

    # Vertical divider left|mid
    vline(c, F_MID_X, FOOTER_Y, FY_TOP, color=colors.HexColor('#2a4a8a'), lw=0.6)

    # ── MIDDLE section: orange strip (left column) + contact info (right) ────
    dept   = data.get('department', '')
    tel    = data.get('tel', '')
    ag     = data.get('agentName', '')
    ag_tel = data.get('agentTel', '')
    em     = data.get('email', '')

    # Orange vertical column on the left of the middle section
    OBC_W = 14 * mm   # orange column width
    rect(c, F_MID_X, FOOTER_Y, OBC_W, FOOTER_H, fill=C_ACCENT, stroke=None)
    # Rotate "お問い合わせ先" 90° inside the orange column
    obc_lbl = 'お問い合わせ先'
    obc_sz  = 8
    c.saveState()
    c.translate(F_MID_X + OBC_W / 2, FOOTER_Y + FOOTER_H / 2)
    c.rotate(90)
    tw_obc = txt_width(obc_lbl, obc_sz, bold=True)
    _draw_rotated_text(c, obc_lbl, -tw_obc / 2, -obc_sz / 2, obc_sz)
    c.restoreState()

    # Contact info to the right of orange column
    CX = F_MID_X + OBC_W + F_PAD
    CW = F_RIGHT_X - CX - F_PAD        # available width for contact text
    cy = FY_TOP - 5

    # Dept label (small, muted)
    if dept:
        draw_text(c, dept, CX, cy, 6, color=colors.HexColor('#aabbd4')); cy -= 8

    # Agent name — auto-sized to fill width
    ag_sz = 8
    if ag:
        for sz in range(16, 7, -1):
            if txt_width(f'【担当】{ag}', sz, bold=True) <= CW:
                ag_sz = sz; break
        draw_bold(c, f'【担当】{ag}', CX, cy, ag_sz, color=C_WHITE); cy -= ag_sz + 3

    # TEL — auto-sized, prominent
    tel_sz = 8
    tel_str = tel or ag_tel
    if tel_str:
        for sz in range(18, 8, -1):
            if txt_width(f'TEL：{tel_str}', sz, bold=True) <= CW:
                tel_sz = sz; break
        draw_bold(c, f'TEL：{tel_str}', CX, cy, tel_sz, color=C_WHITE); cy -= tel_sz + 2

    if ag_tel and ag_tel != tel:
        draw_text(c, f'直通：{ag_tel}', CX, cy, 7, color=C_STEELBL); cy -= 9
    if em:
        draw_text(c, f'✉ {em}', CX, cy, 6.5, color=C_STEELBL)

    # Vertical divider mid|right
    vline(c, F_RIGHT_X, FOOTER_Y, FY_TOP, color=colors.HexColor('#2a4a8a'), lw=0.6)

    # ── RIGHT section: yellow — slogan (top) + 取引態様/手数料 (bottom) ────────
    rect(c, F_RIGHT_X, FOOTER_Y, F_RIGHT_W, FOOTER_H,
         fill=colors.HexColor('#f5c800'), stroke=None)

    slogan = data.get('companySlogan', '')
    ttype  = data.get('transactionType', '')
    fee    = data.get('fee', '')

    slogan_h = FOOTER_H * 0.60
    slogan_y = FOOTER_Y + FOOTER_H - slogan_h
    max_w    = F_RIGHT_W - F_PAD * 2

    if slogan:
        # Auto-size to fill yellow area width
        slogan_sz = 8
        for sz in range(28, 6, -1):
            if txt_width(slogan, sz, bold=True) <= max_w and sz <= slogan_h * 0.80:
                slogan_sz = sz; break
        slogan_draw_y = slogan_y + slogan_h - slogan_sz - 4
        draw_bold(c, slogan, F_RIGHT_X + F_PAD, slogan_draw_y, slogan_sz, color=C_NAVYDK)
        draw_text(c, 'お気軽にご相談ください', F_RIGHT_X + F_PAD,
                  slogan_y + 2, 6.5, color=colors.HexColor('#5a3a00'))

    # Divider line
    hline(c, F_RIGHT_X, W, slogan_y, color=colors.HexColor('#d4aa00'), lw=0.7)

    # BOTTOM: 取引態様 + 手数料 — auto-sized to fill
    bot_parts = []
    if ttype: bot_parts.append(f'【取引態様】{ttype}')
    if fee:   bot_parts.append(f'【手数料】{fee}')
    bot_h = slogan_y - FOOTER_Y
    bot_sz = 7
    if bot_parts:
        full_str = '　'.join(bot_parts)
        for sz in range(16, 6, -1):
            if txt_width(full_str, sz, bold=True) <= max_w and sz * len(bot_parts) <= bot_h * 0.85:
                bot_sz = sz; break
        by2 = slogan_y - 5
        for part in bot_parts:
            draw_bold(c, part, F_RIGHT_X + F_PAD, by2 - bot_sz, bot_sz, color=C_NAVYDK)
            by2 -= bot_sz + 3

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
