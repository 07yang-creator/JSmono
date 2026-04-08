"""
generate_flyer.py  —  Justsalemono
───────────────────────────────────
A4 Japanese real estate flyer generator.

Layout (3 strict zones, never mixed):
  ZONE A  — header + price strip + photo-left / side-info-right
  ZONE B  — property overview table (full-width 4-col)
  ZONE C  — map + floor-plan placeholders + company footer

Dual-font: Helvetica (ASCII ≤U+00FF) + DroidSansFallbackFull (Japanese/CJK).
"""

import json, sys, os, io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from http.server import BaseHTTPRequestHandler

# ── Font resolution ───────────────────────────────────────────────────────────
def _resolve_font():
    candidates = [
        os.environ.get('FONT_PATH', ''),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'fonts', 'DroidSansFallbackFull.ttf'),
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError('DroidSansFallbackFull.ttf not found.')

JP_FONT = 'JP'
LA_FONT = 'Helvetica'
LA_BOLD = 'Helvetica-Bold'
pdfmetrics.registerFont(TTFont(JP_FONT, _resolve_font()))

# ── Dual-font text engine ─────────────────────────────────────────────────────
def is_latin(ch):
    return ord(ch) <= 0x00FF

def txt_width(s, size, bold=False):
    w = 0
    for ch in s:
        f = (LA_BOLD if bold else LA_FONT) if is_latin(ch) else JP_FONT
        w += pdfmetrics.stringWidth(ch, f, size)
    return w

def draw_text(c, s, x, y, size, color=None, align='left', bold=False):
    if not s:
        return
    if color:
        c.setFillColor(color)
    if align in ('center', 'right'):
        w = txt_width(s, size, bold)
        x = (x - w / 2) if align == 'center' else (x - w)
    cur_x = x
    run = ''
    run_lat = None

    def flush(seg, use_lat, cx):
        if not seg:
            return cx
        f = (LA_BOLD if use_lat else JP_FONT) if bold else (LA_FONT if use_lat else JP_FONT)
        c.setFont(f, size)
        c.drawString(cx, y, seg)
        return cx + pdfmetrics.stringWidth(seg, f, size)

    for ch in s:
        lat = is_latin(ch)
        if run_lat is None:
            run_lat = lat
        if lat != run_lat:
            cur_x = flush(run, run_lat, cur_x)
            run, run_lat = ch, lat
        else:
            run += ch
    flush(run, run_lat, cur_x)

def draw_bold(c, s, x, y, size, color=None, align='left'):
    draw_text(c, s, x, y, size, color, align, bold=True)

# ── Colour palette ────────────────────────────────────────────────────────────
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
C_AMBER  = colors.HexColor('#f9d87a')
C_RED    = colors.HexColor('#dc2626')
C_REDBG  = colors.HexColor('#fef2f2')
C_REDBDR = colors.HexColor('#f87171')

# ── Drawing primitives ────────────────────────────────────────────────────────
def rect(c, x, y, w, h, fill=None, stroke=None, lw=0.5):
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(lw)
    c.rect(x, y, w, h, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()

def hline(c, x, y, w, color=C_DIV, lw=0.4):
    c.saveState()
    c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x, y, x + w, y)
    c.restoreState()


# ── Main generator ────────────────────────────────────────────────────────────
def generate(data: dict, out):
    c = canvas.Canvas(out, pagesize=A4)
    W, H = A4
    MX = 14 * mm          # horizontal margin
    MY = 9  * mm          # bottom margin
    IW = W - 2 * MX       # inner width  ≈ 515.9 pts

    # ═══════════════════════════════════════════════════════════════════════════
    # ZONE A  —  HEADER + PRICE + PHOTO/SIDE-INFO
    # ═══════════════════════════════════════════════════════════════════════════

    # ── A1. HEADER BAR ────────────────────────────────────────────────────────
    BH = 20 * mm                         # header height
    bar_bot = H - BH                     # y of header bottom edge
    rect(c, 0, bar_bot, W, BH, fill=C_NAVY)

    # Property-type badge (orange pill)
    prop_type = data.get('propertyType', '中古戸建')
    bw = txt_width(prop_type, 9) + 14
    rect(c, MX, bar_bot + 8, bw, 13, fill=C_ACCENT)
    draw_text(c, prop_type, MX + 7, bar_bot + 13, 9, color=C_WHITE)

    # Short address (bold white, next to badge)
    addr_raw = data.get('address', '')
    short = addr_raw.replace('東京都','').replace('大阪府','').replace('神奈川県','')[:26]
    draw_bold(c, short, MX + bw + 10, bar_bot + 13, 12, color=C_WHITE)

    # Brand name (top-right)
    brand = data.get('brandName', data.get('companyName', ''))
    draw_text(c, brand, W - MX, bar_bot + 13, 8, color=C_STEELBL, align='right')

    # Stations — all on one line, bottom of header
    st_parts = []
    for st in data.get('stations', [])[:3]:
        ln  = st.get('line', '')
        stn = st.get('station', '').replace('駅', '')
        wk  = st.get('walk', '')
        st_parts.append(f"{ln} 『{stn}』駅 徒歩{wk}分")
    draw_text(c, '　'.join(st_parts), MX, bar_bot + 4, 7, color=C_DARKBL)

    cur_y = bar_bot - 2 * mm

    # ── A2. PRICE STRIP ───────────────────────────────────────────────────────
    PSH = 15 * mm                        # price strip height
    price_bot = cur_y - PSH
    rect(c, 0, price_bot, W, PSH, fill=C_LBLUE)

    draw_text(c, '販売価格', MX, cur_y - 5, 7, color=C_MUTED)

    price_raw = data.get('price', '')
    num_part  = price_raw.replace('万円', '').strip()
    tax_lbl   = '万円（税込）' if '税込' in data.get('taxIncluded', '税込') else '万円（税別）'
    py = price_bot + 7
    draw_bold(c, num_part, MX, py, 24, color=C_ACCENT)
    draw_text(c, tax_lbl, MX + txt_width(num_part, 24, bold=True) + 4, py + 2, 10, color=C_ACCENT)

    rebuild = data.get('rebuild', '')
    if rebuild:
        rbw = txt_width(rebuild, 8) + 12
        rect(c, W - MX - rbw, py, rbw, 13, fill=C_REDBG, stroke=C_REDBDR, lw=0.8)
        draw_text(c, rebuild, W - MX - rbw + 6, py + 4, 8, color=C_RED)

    cur_y = price_bot - 3 * mm

    # ── A3. PHOTO (left 57%) + SIDE INFO (right 43%) ─────────────────────────
    IMG_H  = 60 * mm
    IMG_W  = IW * 0.57
    GAP    = 3.5 * mm
    SIDE_X = MX + IMG_W + GAP
    SIDE_W = IW - IMG_W - GAP
    img_bot = cur_y - IMG_H

    # Photo placeholder (left)
    rect(c, MX, img_bot, IMG_W, IMG_H,
         fill=colors.HexColor('#c8d4e8'), stroke=C_DIV, lw=0.5)
    draw_text(c, '外　観',
              MX + IMG_W / 2, img_bot + IMG_H / 2 + 6,
              16, color=colors.HexColor('#7a8faa'), align='center')
    draw_text(c, '（写真をここに挿入）',
              MX + IMG_W / 2, img_bot + IMG_H / 2 - 10,
              8,  color=colors.HexColor('#8899bb'), align='center')

    # Side info panel (right upper) — lease / status / nearby
    sy = cur_y

    lease = data.get('leasePeriod', '')
    grent = data.get('groundRent', '')
    if lease or grent:
        lbh = 30
        rect(c, SIDE_X, sy - lbh, SIDE_W, lbh,
             fill=colors.HexColor('#fff7ed'),
             stroke=colors.HexColor('#fed7aa'), lw=0.7)
        draw_bold(c, '借地期間', SIDE_X + 4, sy - 8, 7.5, color=C_ACCENT)
        if grent:
            gx = SIDE_X + txt_width('借地期間', 7.5, bold=True) + 8
            draw_text(c, f'地代　{grent}', gx, sy - 8, 7.5, color=C_BLACK)
        if lease:
            draw_text(c, lease, SIDE_X + 4, sy - lbh + 7, 7, color=C_BLACK)
        sy -= lbh + 2

    status   = data.get('currentStatus', '')
    handover = data.get('handover', '')
    if status or handover:
        rect(c, SIDE_X, sy - 12, SIDE_W, 12, fill=C_MBLUE)
        draw_text(c, f'現況：{status}　引渡：{handover}',
                  SIDE_X + 4, sy - 9, 7.5, color=C_NAVY)
        sy -= 14

    nearby = data.get('nearby', [])
    if nearby:
        draw_bold(c, '周辺環境', SIDE_X + 2, sy - 9, 8, color=C_NAVY)
        ny_y = sy - 21
        for nb in nearby[:8]:
            nm = nb.get('name', '')
            wk = nb.get('walk', '')
            draw_text(c, f'・{nm}', SIDE_X + 3, ny_y, 7, color=C_BLACK)
            draw_text(c, wk, SIDE_X + SIDE_W - 2, ny_y, 7,
                      color=C_MUTED, align='right')
            ny_y -= 9
            if ny_y < img_bot + 4:
                break

    # School zone below nearby (if fits)
    school = ''
    if data.get('elemSchool'):
        school += f"小：{data['elemSchool']} {data.get('elemSchoolDist','')}　"
    if data.get('juniorSchool'):
        school += f"中：{data['juniorSchool']} {data.get('juniorSchoolDist','')}"
    if school and ny_y > img_bot + 10:
        draw_bold(c, '学区', SIDE_X + 2, ny_y - 2, 7.5, color=C_NAVY)
        draw_text(c, school.strip(), SIDE_X + txt_width('学区', 7.5, bold=True) + 6,
                  ny_y - 2, 7, color=C_BLACK)

    cur_y = img_bot - 4 * mm

    # ═══════════════════════════════════════════════════════════════════════════
    # ZONE B  —  PROPERTY TABLE  (full-width 4-column grid)
    # ═══════════════════════════════════════════════════════════════════════════
    HALF = IW / 2
    LBW  = HALF * 0.30     # label cell width (per half)
    VLW  = HALF * 0.70     # value cell width (per half)
    RH   = 12              # row height (pts)
    RX   = MX + HALF       # right-half start x

    def row4(ll, lv, rl, rv, alt=False):
        """One 4-column row: label|value|label|value."""
        nonlocal cur_y
        bg = C_LBLUE if alt else C_WHITE
        rect(c, MX,       cur_y, LBW, RH, fill=C_SECBG, stroke=C_DIV, lw=0.3)
        draw_text(c, ll,  MX + 3,       cur_y + 3, 7.5, color=C_NAVY)
        rect(c, MX + LBW, cur_y, VLW, RH, fill=bg,     stroke=C_DIV, lw=0.3)
        draw_text(c, lv,  MX + LBW + 4, cur_y + 3, 7.5, color=C_BLACK)
        rect(c, RX,       cur_y, LBW, RH, fill=C_SECBG, stroke=C_DIV, lw=0.3)
        draw_text(c, rl,  RX + 3,       cur_y + 3, 7.5, color=C_NAVY)
        rect(c, RX + LBW, cur_y, VLW, RH, fill=bg,     stroke=C_DIV, lw=0.3)
        draw_text(c, rv,  RX + LBW + 4, cur_y + 3, 7.5, color=C_BLACK)
        cur_y -= RH

    def row_full(ll, lv, alt=False):
        """One full-width 2-column row: label|value."""
        nonlocal cur_y
        FLW = IW * 0.145
        FVW = IW * 0.855
        bg  = C_LBLUE if alt else C_WHITE
        rect(c, MX,       cur_y, FLW, RH, fill=C_SECBG, stroke=C_DIV, lw=0.3)
        draw_text(c, ll,  MX + 3,       cur_y + 3, 7.5, color=C_NAVY)
        rect(c, MX + FLW, cur_y, FVW, RH, fill=bg,     stroke=C_DIV, lw=0.3)
        draw_text(c, lv,  MX + FLW + 4, cur_y + 3, 7.5, color=C_BLACK)
        cur_y -= RH

    # Land-area string
    la_str = ''
    if data.get('landArea'):
        la_str = f"{data['landArea']}㎡"
        if data.get('landAreaTsubo'):
            la_str += f" ({data['landAreaTsubo']}坪)"

    # Floor-area string
    fa_parts = [data.get(f'floorArea{i}', '') for i in range(1, 5)]
    fa_str = '　'.join(p for p in fa_parts if p)
    total_fa = f"{data['totalFloorArea']}㎡" if data.get('totalFloorArea') else ''

    # — Property overview rows —
    row4('所在地',   addr_raw,
         '築年月',   data.get('builtYear', ''))
    row4('土地面積', la_str,
         '構造',     data.get('structure', ''),       alt=True)
    row4('土地権利', data.get('landRight', ''),
         '床面積',   fa_str)
    row4('地目',     data.get('landCategory', ''),
         '合計',     total_fa,                         alt=True)
    row4('接面道路', data.get('frontRoad', ''),
         '間取り',   data.get('layout', '－'))
    row4('再建築',   data.get('rebuild', ''),
         '現況',     data.get('currentStatus', ''),    alt=True)

    # Thin divider between overview and legal
    hline(c, MX, cur_y + 1, IW, color=C_DIV, lw=0.6)

    # — Legal restriction rows —
    row4('都市計画', data.get('cityPlan', ''),
         '建ぺい率', data.get('bcr', ''))
    row4('用途地域', data.get('useZone', ''),
         '容積率',   data.get('far', ''),              alt=True)
    row4('防火指定', data.get('fireZone', ''),
         '高度地区', data.get('heightDistrict', ''))

    other = data.get('otherLegal', '')
    if other:
        row_full('その他', other, alt=True)

    # — Utilities & remarks (full-width rows) —
    utils_parts = []
    if data.get('electric'): utils_parts.append(f"電気：{data['electric']}")
    if data.get('gas'):      utils_parts.append(f"ガス：{data['gas']}")
    if data.get('water'):    utils_parts.append(f"水道：{data['water']}")
    if utils_parts:
        row_full('ライフライン', '　'.join(utils_parts))

    for i, rem in enumerate(data.get('remarks', '').split('\n')):
        if rem.strip():
            row_full('備考', rem.strip(), alt=(i % 2 == 1))

    # Note line
    cur_y -= 3
    draw_text(c, '現況と図面が相違する場合は現況を優先します。',
              MX, cur_y, 6.5, color=C_MUTED)
    cur_y -= 10

    # ═══════════════════════════════════════════════════════════════════════════
    # ZONE C  —  MAP/FLOORPLAN + COMPANY FOOTER  (bottom anchor)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── C1. FOOTER BAR (drawn first to anchor bottom) ─────────────────────────
    FOOTER_H = 26 * mm
    FOOTER_Y = MY
    rect(c, 0, FOOTER_Y, W, FOOTER_H, fill=C_NAVYDK)

    # Left block: brand → company → store+agent
    fy = FOOTER_Y + FOOTER_H - 5
    if brand:
        draw_bold(c, brand, MX, fy, 10, color=C_WHITE)
        # underline accent
        ul_w = txt_width(brand, 10, bold=True)
        c.saveState()
        c.setStrokeColor(C_ACCENT); c.setLineWidth(0.8)
        c.line(MX, fy - 1, MX + ul_w, fy - 1)
        c.restoreState()
        fy -= 13
    co = data.get('companyName', '')
    if co and co != brand:
        draw_text(c, co, MX, fy, 8, color=C_STEELBL)
        fy -= 11
    ag = data.get('agentName', '')
    store_line = brand if brand else co
    if ag:
        draw_text(c, f'{store_line} 【担当】 {ag}', MX, fy, 7, color=C_STEELBL)

    # Centre block: transaction / fee
    cx2 = W / 2
    tt  = data.get('transactionType', '')
    fee = data.get('fee', '')
    if tt:
        draw_text(c, f'取引態様：{tt}', cx2, FOOTER_Y + FOOTER_H - 9,
                  7.5, color=C_WHITE, align='center')
    if fee:
        draw_text(c, f'手数料：{fee}', cx2, FOOTER_Y + FOOTER_H - 20,
                  7.5, color=C_WHITE, align='center')

    # Right block: catchcopy → agent → TEL → FAX → email
    ry = FOOTER_Y + FOOTER_H - 5
    cp = data.get('catchcopy', '')
    if cp:
        draw_text(c, cp, W - MX, ry, 7, color=C_AMBER, align='right')
        ry -= 10
    if ag:
        draw_text(c, f'【担当】{ag}', W - MX, ry, 8, color=C_WHITE, align='right')
        ry -= 11
    tel = data.get('tel', '')
    if tel:
        draw_bold(c, f'TEL：{tel}', W - MX, ry, 10, color=C_WHITE, align='right')
        ry -= 12
    fax = data.get('fax', '')
    if fax:
        draw_text(c, f'FAX：{fax}', W - MX, ry, 7.5, color=C_STEELBL, align='right')
        ry -= 9
    em = data.get('email', '')
    if em:
        draw_text(c, em, W - MX, ry, 7, color=C_STEELBL, align='right')

    # License line (below footer)
    lic = data.get('licenseNo', '')
    if lic:
        draw_text(c, lic, MX, FOOTER_Y - 7, 6, color=C_MUTED)

    # ── C2. MAP + FLOOR-PLAN PLACEHOLDERS (fill space between table and footer) ─
    MAP_BOT = FOOTER_Y + FOOTER_H + 4 * mm
    MAP_TOP = cur_y - 2 * mm
    MAP_H   = MAP_TOP - MAP_BOT

    if MAP_H > 18:
        MH  = (IW - 3 * mm) / 2
        mid = MAP_BOT + MAP_H / 2

        # Left: map
        rect(c, MX, MAP_BOT, MH, MAP_H,
             fill=colors.HexColor('#e8eef6'), stroke=C_DIV, lw=0.5)
        draw_text(c, '周辺地図',
                  MX + MH / 2, mid + 6, 13,
                  color=colors.HexColor('#8899bb'), align='center')
        draw_text(c, '（地図を挿入）',
                  MX + MH / 2, mid - 10, 8,
                  color=colors.HexColor('#8899bb'), align='center')

        # Right: floor plan
        FPX = MX + MH + 3 * mm
        rect(c, FPX, MAP_BOT, MH, MAP_H,
             fill=colors.HexColor('#eef3e8'), stroke=C_DIV, lw=0.5)
        draw_text(c, '間取り図',
                  FPX + MH / 2, mid + 6, 13,
                  color=colors.HexColor('#88aa88'), align='center')
        draw_text(c, '（間取り図を挿入）',
                  FPX + MH / 2, mid - 10, 8,
                  color=colors.HexColor('#88aa88'), align='center')

    c.save()


# ── Vercel serverless handler ────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            data   = json.loads(body)
            buf    = io.BytesIO()
            generate(data, buf)
            pdf = buf.getvalue()
            self.send_response(200)
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Disposition', 'attachment; filename="flyer.pdf"')
            self.send_header('Content-Length', str(len(pdf)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(pdf)
        except Exception as e:
            msg = str(e).encode()
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, format, *args):
        pass   # suppress default access log noise


# ── CLI  (python generate_flyer.py data.json output.pdf) ────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python generate_flyer.py data.json output.pdf')
        sys.exit(1)
    with open(sys.argv[1], encoding='utf-8') as f:
        generate(json.load(f), sys.argv[2])
