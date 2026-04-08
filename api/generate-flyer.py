"""
generate_flyer.py  —  Justsalemono
───────────────────────────────────
Generates an A4 Japanese real estate advertisement flyer (PDF).
Uses a dual-font engine: Helvetica (embedded) for ASCII/Latin,
DroidSansFallbackFull (embedded TTF) for Japanese/CJK/fullwidth.

Deploy as:  POST /api/generate-flyer
Input:      application/json  (property data dict)
Output:     application/pdf
CLI:        python generate_flyer.py data.json output.pdf
"""

import json, sys, os
from reportlab.lib.pagesizes import A4

# ── Font path: env var (Vercel) → bundled relative → system fallback ─────────
def _resolve_font():
    candidates = [
        os.environ.get('FONT_PATH', ''),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts', 'DroidSansFallbackFull.ttf'),
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError('DroidSansFallbackFull.ttf not found. Add it to /fonts/ or set FONT_PATH.')
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Fonts ────────────────────────────────────────────────────────────────────
JP_TTF  = _resolve_font()
JP_FONT = 'JP'
LA_FONT = 'Helvetica'          # built-in, no registration needed
LA_BOLD = 'Helvetica-Bold'
pdfmetrics.registerFont(TTFont(JP_FONT, JP_TTF))

def is_latin(ch):
    """True for basic ASCII + Latin-1 (U+0000–U+00FF)."""
    return ord(ch) <= 0x00FF

def txt_width(s, size):
    """Width of mixed string at given size."""
    w = 0
    for ch in s:
        f = LA_FONT if is_latin(ch) else JP_FONT
        w += pdfmetrics.stringWidth(ch, f, size)
    return w

def draw_text(c, s, x, y, size, color=None, align='left'):
    """Draw mixed Japanese/Latin string with per-character font switching."""
    if not s:
        return
    if color:
        c.setFillColor(color)

    # Measure for alignment
    if align in ('center', 'right'):
        w = txt_width(s, size)
        if align == 'center':
            x = x - w / 2
        else:
            x = x - w

    cur_x = x
    run = ''
    run_lat = None

    def flush(seg, use_lat, cx):
        if not seg:
            return cx
        font = LA_FONT if use_lat else JP_FONT
        c.setFont(font, size)
        c.drawString(cx, y, seg)
        return cx + pdfmetrics.stringWidth(seg, font, size)

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

def draw_text_bold(c, s, x, y, size, color=None, align='left'):
    """Draw with bold Latin font (JP font has no bold variant)."""
    if not s:
        return
    if color:
        c.setFillColor(color)
    if align in ('center', 'right'):
        w = txt_width(s, size)
        x = x - w / 2 if align == 'center' else x - w
    cur_x = x
    run = ''
    run_lat = None
    def flush(seg, use_lat, cx):
        if not seg: return cx
        font = LA_BOLD if use_lat else JP_FONT
        c.setFont(font, size)
        c.drawString(cx, y, seg)
        return cx + pdfmetrics.stringWidth(seg, font, size)
    for ch in s:
        lat = is_latin(ch)
        if run_lat is None: run_lat = lat
        if lat != run_lat:
            cur_x = flush(run, run_lat, cur_x)
            run, run_lat = ch, lat
        else:
            run += ch
    flush(run, run_lat, cur_x)

# ── Colour palette ────────────────────────────────────────────────────────────
C_NAVY    = colors.HexColor('#1a4fa0')
C_NAVYDK  = colors.HexColor('#12357a')
C_ACCENT  = colors.HexColor('#e85d2f')
C_GOLD    = colors.HexColor('#c8971a')
C_LBLUE   = colors.HexColor('#eef3fb')
C_MBLUE   = colors.HexColor('#d8e4f5')
C_SECBG   = colors.HexColor('#dde8f8')
C_WHITE   = colors.white
C_BLACK   = colors.HexColor('#1c2333')
C_MUTED   = colors.HexColor('#5a6480')
C_DIV     = colors.HexColor('#c0cfe8')
C_GREEN   = colors.HexColor('#16a34a')
C_RED     = colors.HexColor('#dc2626')
C_REDBG   = colors.HexColor('#fef2f2')
C_REDBDR  = colors.HexColor('#f87171')
C_AMBER   = colors.HexColor('#f9d87a')
C_STEELBL = colors.HexColor('#adc4e8')
C_DARKBL  = colors.HexColor('#c8d8f0')

W, H      = A4
MX        = 14 * mm    # horizontal margin
MY        = 9  * mm    # bottom margin
IW        = W - 2 * MX  # inner width


# ── Drawing primitives ────────────────────────────────────────────────────────

def rect(c, x, y, w, h, fill=None, stroke=None, lw=0.5):
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(lw)
    c.rect(x, y, w, h, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()

def hline(c, x, y, w, color=C_DIV, lw=0.4):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    c.line(x, y, x + w, y)
    c.restoreState()

def section_bar(c, label, x, y, w, h=13):
    """Draws a dark-navy section header bar. Returns top-of-bar y."""
    rect(c, x, y, w, h, fill=C_NAVY)
    draw_text(c, label, x + 6, y + 3.5, 8.5, color=C_WHITE)
    return y + h

def table_row(c, label, value, x, y, lw, vw, rh=12, alt=False):
    """Draws a label | value row. Returns y BELOW the row."""
    bg = C_LBLUE if alt else C_WHITE
    rect(c, x,      y, lw, rh, fill=C_SECBG, stroke=C_DIV, lw=0.3)
    rect(c, x + lw, y, vw, rh, fill=bg,      stroke=C_DIV, lw=0.3)
    draw_text(c, label, x + 3,      y + 3, 7.5, color=C_NAVY)
    draw_text(c, value, x + lw + 4, y + 3, 7.5, color=C_BLACK)
    return y - rh


# ── Main generator ─────────────────────────────────────────────────────────────

def generate(data: dict, out_path: str):
    c = canvas.Canvas(out_path, pagesize=A4)

    # ── 1. HEADER BANNER ────────────────────────────────────────────────────
    BH = 26 * mm
    rect(c, 0, H - BH, W, BH, fill=C_NAVY)

    # Property-type badge
    prop_type = data.get('propertyType', '中古戸建')
    bw = txt_width(prop_type, 9) + 14
    rect(c, MX, H - BH + 10, bw, 13, fill=C_ACCENT)
    draw_text(c, prop_type, MX + 7, H - BH + 14, 9, color=C_WHITE)

    # Short address
    addr_raw = data.get('address', '')
    short = addr_raw.replace('東京都','').replace('大阪府','').replace('神奈川県','')[:22]
    draw_text(c, short, MX + bw + 8, H - BH + 14, 11, color=C_WHITE)

    # Brand top-right
    brand = data.get('brandName', data.get('companyName', ''))
    draw_text(c, brand, W - MX, H - BH + 14, 8, color=C_STEELBL, align='right')

    # Station strip
    sx = MX
    for st in data.get('stations', [])[:3]:
        entry = f"{st.get('line','')} 『{st.get('station','').replace('駅','')}』駅 徒歩{st.get('walk','')}分"
        draw_text(c, entry, sx, H - BH + 3, 7.5, color=C_DARKBL)
        sx += txt_width(entry, 7.5) + 14
        if sx > W - MX - 40: break

    cur_y = H - BH - 4 * mm

    # ── 2. PRICE STRIP ──────────────────────────────────────────────────────
    PH = 16 * mm
    rect(c, 0, cur_y - PH, W, PH, fill=C_LBLUE)

    # "販売価格" label — small tag at TOP of strip
    draw_text(c, '販売価格', MX, cur_y - 8, 7, color=C_MUTED)

    # Large price number — sits in lower 2/3 of strip
    price_raw = data.get('price', '')
    num_part  = price_raw.replace('万円','').strip()   # keep commas e.g. "1,480"
    tax_label = '万円（税込）' if '税込' in data.get('taxIncluded', '税込') else '万円（税別）'
    price_y   = cur_y - PH + 10            # baseline sits near the bottom of strip
    draw_text_bold(c, num_part, MX, price_y, 24, color=C_ACCENT)
    px = MX + txt_width(num_part, 24)
    draw_text(c, tax_label, px + 3, price_y + 2, 10, color=C_ACCENT)

    # Rebuild badge — vertically centred on price row
    rebuild = data.get('rebuild', '')
    if rebuild:
        rbw = txt_width(rebuild, 8) + 12
        bh  = 13
        by  = price_y - 2
        rect(c, W - MX - rbw, by, rbw, bh, fill=C_REDBG, stroke=C_REDBDR, lw=0.8)
        draw_text(c, rebuild, W - MX - rbw + 6, by + 3, 8, color=C_RED)

    cur_y -= PH + 3 * mm

    # ── 3. PHOTO + SIDE INFO ────────────────────────────────────────────────
    PW    = IW * 0.56
    PH2   = 62 * mm
    px_   = MX
    py_   = cur_y - PH2

    rect(c, px_, py_, PW, PH2, fill=colors.HexColor('#c8d4e8'), stroke=C_DIV, lw=0.5)
    draw_text(c, '外　観', px_ + PW/2, py_ + PH2/2 + 3, 18,
              color=colors.HexColor('#7a8faa'), align='center')
    draw_text(c, '（写真をここに挿入）', px_ + PW/2, py_ + PH2/2 - 12, 8,
              color=colors.HexColor('#8899bb'), align='center')

    # Right side info panel
    sx2  = px_ + PW + 4 * mm
    sw2  = IW - PW - 4 * mm
    sy2  = cur_y

    # Lease period box — tight fit, only as tall as the content needs
    lease = data.get('leasePeriod', '')
    grent = data.get('groundRent', '')
    if lease:
        lbh = 24 if grent else 17        # height in POINTS
        rect(c, sx2, sy2 - lbh, sw2, lbh,
             fill=colors.HexColor('#fff7ed'), stroke=colors.HexColor('#fed7aa'), lw=0.7)
        draw_text(c, '◆ 借地期間', sx2 + 4, sy2 - 8,  7.5, color=C_ACCENT)
        draw_text(c, lease,        sx2 + 4, sy2 - lbh + 4, 7, color=C_BLACK)
        if grent:
            draw_text(c, '地代　' + grent, sx2 + txt_width('◆ 借地期間', 7.5) + 8,
                      sy2 - 8, 7, color=C_BLACK)
        sy2 -= lbh + 3

    # Status bar
    status   = data.get('currentStatus', '')
    handover = data.get('handover', '')
    if status:
        rect(c, sx2, sy2 - 9, sw2, 9, fill=C_MBLUE)
        draw_text(c, f'現況：{status}　引渡：{handover}', sx2 + 4, sy2 - 7, 7.5, color=C_NAVY)
        sy2 -= 11

    # Nearby list
    nearby = data.get('nearby', [])
    if nearby:
        draw_text(c, '◆ 周辺環境', sx2 + 2, sy2 - 6, 7.5, color=C_NAVY)
        ny_y = sy2 - 15
        for nb in nearby[:6]:
            nm = nb.get('name','')
            wk = nb.get('walk','')
            draw_text(c, f'・{nm}', sx2 + 3, ny_y, 7, color=C_BLACK)
            draw_text(c, wk, sx2 + sw2 - 2, ny_y, 7, color=C_MUTED, align='right')
            ny_y -= 8.5
            if ny_y < py_: break

    cur_y = py_ - 3 * mm

    # ── 4. PROPERTY OVERVIEW TABLE ──────────────────────────────────────────
    section_bar(c, '■ 物件概要', MX, cur_y, IW)
    cur_y -= 1

    cw   = IW / 2
    lw_  = cw * 0.32
    vw_  = cw * 0.68
    rh_  = 13

    ly_ = cur_y
    ry_ = cur_y
    rx_ = MX + cw

    def tl(lbl, val, alt=False):
        nonlocal ly_
        ly_ = table_row(c, lbl, val, MX, ly_, lw_, vw_, rh_, alt)

    def tr(lbl, val, alt=False):
        nonlocal ry_
        ry_ = table_row(c, lbl, val, rx_, ry_, lw_, vw_, rh_, alt)

    tl('■ 所在地',   addr_raw)
    tl('■ 土地面積', f"{data.get('landArea','')}㎡ ({data.get('landAreaTsubo','')}坪)")
    tl('■ 土地権利', data.get('landRight',''),  alt=True)
    tl('■ 地目',     data.get('landCategory',''))
    tl('■ 接面道路', data.get('frontRoad',''),   alt=True)
    tl('■ 再建築',   data.get('rebuild',''))

    tr('■ 築年月',   data.get('builtYear',''))
    tr('■ 構造',     data.get('structure',''))
    floors = '  '.join([data.get(f'floorArea{i}','') for i in range(1,4) if data.get(f'floorArea{i}')])
    tr('■ 床面積',   floors,                    alt=True)
    tr('■ 合計',     f"{data.get('totalFloorArea','')}㎡")
    tr('■ 間取り',   data.get('layout','－'),    alt=True)
    tr('■ 現況',     data.get('currentStatus',''))

    cur_y = min(ly_, ry_) - 3

    # ── 5. LEGAL RESTRICTIONS ────────────────────────────────────────────────
    section_bar(c, '■ 法令制限', MX, cur_y, IW)
    cur_y -= 1

    half  = IW / 2
    llw   = half * 0.32
    lvw   = half * 0.68
    rh2   = 13
    ll_y  = cur_y
    rl_y  = cur_y
    rl_x  = MX + half

    def ll(lbl, val, alt=False):
        nonlocal ll_y
        ll_y = table_row(c, lbl, val, MX,   ll_y, llw, lvw, rh2, alt)

    def rl(lbl, val, alt=False):
        nonlocal rl_y
        rl_y = table_row(c, lbl, val, rl_x, rl_y, llw, lvw, rh2, alt)

    ll('都市計画', data.get('cityPlan',''))
    ll('用途地域', data.get('useZone',''))
    ll('防火指定', data.get('fireZone',''), alt=True)

    rl('建ぺい率', data.get('bcr',''))
    rl('容積率',   data.get('far',''))
    rl('高度地区', data.get('heightDistrict',''), alt=True)

    cur_y = min(ll_y, rl_y)
    other = data.get('otherLegal','')
    if other:
        cur_y = table_row(c, 'その他', other, MX, cur_y, IW*0.16, IW*0.84, rh2)

    cur_y -= 3

    # ── 6. UTILITIES & REMARKS ───────────────────────────────────────────────
    section_bar(c, '■ ライフライン・備考', MX, cur_y, IW)
    cur_y -= 1

    utils = '　'.join(filter(None, [
        f"電気：{data.get('electric','')}" if data.get('electric') else '',
        f"ガス：{data.get('gas','')}"      if data.get('gas')      else '',
        f"水道：{data.get('water','')}"    if data.get('water')    else '',
    ]))
    cur_y = table_row(c, 'ライフライン', utils, MX, cur_y, IW*0.16, IW*0.84, rh2)

    for i, rem in enumerate(data.get('remarks','').split('\n')):
        if rem.strip():
            cur_y = table_row(c, '備考', rem.strip(), MX, cur_y, IW*0.16, IW*0.84, rh2, alt=(i%2==0))

    school = ''
    if data.get('elemSchool'):
        school += f"小：{data['elemSchool']} {data.get('elemSchoolDist','')}　"
    if data.get('juniorSchool'):
        school += f"中：{data['juniorSchool']} {data.get('juniorSchoolDist','')}"
    if school:
        cur_y = table_row(c, '学区', school.strip(), MX, cur_y, IW*0.16, IW*0.84, rh2)

    cur_y -= 4
    draw_text(c, '※現況と図面が相違する場合は現況を優先します。', MX, cur_y, 6.5, color=C_MUTED)
    cur_y -= 9

    # ── 7. MAP PLACEHOLDER (fills remaining space above footer) ─────────────
    FH     = 25 * mm
    FY     = MY
    map_y  = FY + FH + 6 * mm          # top of map = bottom of available space
    map_h  = cur_y - map_y - 2 * mm    # height = whatever is left
    if map_h > 20:                      # only draw if there's meaningful space
        map_half = (IW - 3 * mm) / 2
        # Left: map placeholder
        rect(c, MX, map_y, map_half, map_h,
             fill=colors.HexColor('#e8eef6'), stroke=C_DIV, lw=0.5)
        draw_text(c, '周辺地図', MX + map_half/2, map_y + map_h/2 + 4, 13,
                  color=colors.HexColor('#8899bb'), align='center')
        draw_text(c, '（地図を挿入）', MX + map_half/2, map_y + map_h/2 - 10, 8,
                  color=colors.HexColor('#8899bb'), align='center')
        # Right: map placeholder 2 (interior/floor plan)
        rx = MX + map_half + 3 * mm
        rect(c, rx, map_y, map_half, map_h,
             fill=colors.HexColor('#eef3e8'), stroke=C_DIV, lw=0.5)
        draw_text(c, '間取り図', rx + map_half/2, map_y + map_h/2 + 4, 13,
                  color=colors.HexColor('#88aa88'), align='center')
        draw_text(c, '（間取り図を挿入）', rx + map_half/2, map_y + map_h/2 - 10, 8,
                  color=colors.HexColor('#88aa88'), align='center')

    # ── 8. FOOTER BAR ────────────────────────────────────────────────────────
    rect(c, 0, FY, W, FH, fill=C_NAVYDK)

    fy = FY + FH - 5
    if brand:
        draw_text_bold(c, brand, MX, fy, 10, color=C_WHITE)
        fy -= 12
    co = data.get('companyName','')
    if co and co != brand:
        draw_text(c, co, MX, fy, 8, color=C_STEELBL)
        fy -= 10
    ca = data.get('companyAddress','')
    if ca:
        draw_text(c, ca, MX, fy, 6.5, color=C_STEELBL)

    # Right side: catchcopy + agent + contact
    ry2 = FY + FH - 5
    cp  = data.get('catchcopy','')
    if cp:
        draw_text(c, cp, W - MX, ry2, 7, color=C_AMBER, align='right')
        ry2 -= 10
    ag = data.get('agentName','')
    if ag:
        draw_text(c, f'【担当】{ag}', W - MX, ry2, 8, color=C_WHITE, align='right')
        ry2 -= 10
    tel = data.get('tel','')
    if tel:
        draw_text_bold(c, f'TEL：{tel}', W - MX, ry2, 9, color=C_WHITE, align='right')
        ry2 -= 10
    fax = data.get('fax','')
    if fax:
        draw_text(c, f'FAX：{fax}', W - MX, ry2, 7.5, color=C_STEELBL, align='right')
        ry2 -= 9
    em = data.get('email','')
    if em:
        draw_text(c, em, W - MX, ry2, 7, color=C_STEELBL, align='right')

    # Centre: transaction / fee
    cx2 = W / 2
    tt  = data.get('transactionType','')
    fee = data.get('fee','')
    if tt:
        draw_text(c, f'取引態様：{tt}', cx2, FY + FH - 7,  7.5, color=C_WHITE, align='center')
    if fee:
        draw_text(c, f'手数料：{fee}',  cx2, FY + FH - 18, 7.5, color=C_WHITE, align='center')

    # ── 8. LICENSE LINE ──────────────────────────────────────────────────────
    lic = data.get('licenseNo','')
    if lic:
        draw_text(c, lic, MX, FY - 6, 6, color=C_MUTED)

    c.save()
    print(f'✅  {out_path}')


# ── Vercel handler (BaseHTTPRequestHandler) ──────────────────────────────────

import tempfile
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get('content-length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as t:
                tmp_path = t.name

            generate(data, tmp_path)

            with open(tmp_path, 'rb') as f:
                pdf_bytes = f.read()
            os.unlink(tmp_path)

            # Derive filename from address
            addr = data.get('address', '物件').replace(' ', '_')[:20]
            filename = f"{addr}_チラシ.pdf"

            self._cors()
            self.send_response(200)
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Disposition',
                             f'attachment; filename="{filename}"')
            self.send_header('Content-Length', str(len(pdf_bytes)))
            self.end_headers()
            self.wfile.write(pdf_bytes)

        except Exception as e:
            msg = str(e).encode('utf-8')
            self._send(500, msg)

    def _send(self, code, body: bytes):
        self._cors()
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, fmt, *args):
        pass  # silence default access log


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python generate_flyer.py data.json output.pdf')
        sys.exit(1)
    with open(sys.argv[1], encoding='utf-8') as f:
        generate(json.load(f), sys.argv[2])
