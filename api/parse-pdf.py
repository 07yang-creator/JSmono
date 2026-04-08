"""
parse_pdf.py
────────────
Extracts structured property data from a Japanese real estate PDF data sheet.
Returns a JSON object matching the form fields in index.html.

Deploy as:  POST /api/parse-pdf   (Vercel serverless or FastAPI route)
Input:      multipart/form-data   field name: "file"
Output:     application/json
"""

import re
import json
import pdfplumber


# ── Helper patterns ──────────────────────────────────────────────────────────

PRICE_RE      = re.compile(r'([\d,，]+)\s*万円')
LAND_AREA_RE  = re.compile(r'([\d.]+)\s*㎡')
TSUBO_RE      = re.compile(r'([\d.]+)\s*坪')
FLOOR_RE      = re.compile(r'(\d+)階\s*([\d.]+)\s*㎡')
TOTAL_FLOOR_RE= re.compile(r'合計\s*([\d.]+)\s*㎡')
BCR_RE        = re.compile(r'建ぺい率[：:]\s*(\d+)%')
FAR_RE        = re.compile(r'容[^%\n]{0,10}率[^%\n]{0,5}[：:]\s*(\d+)%')
STATION_RE    = re.compile(r'((?:JR|地下鉄|東急|西武|京急|阪急|近鉄|南海|名鉄|相鉄|東京メトロ|都営|小田急|京王|京成|つくばエクスプレス|TX|りんかい|ゆりかもめ)?[\w]+線)\s*[『「](.*?)[』」]駅\s*徒歩\s*(\d+)\s*分')
NEARBY_RE     = re.compile(r'[・•]\s*([^\s徒]+)\s*(徒歩約?\s*\d+\s*分)')
TEL_RE        = re.compile(r'TEL[：:]\s*([\d\-（）\s]+)')
FAX_RE        = re.compile(r'FAX[：:]\s*([\d\-（）\s]+)')
EMAIL_RE      = re.compile(r'[✉📧]?\s*([\w.\-]+@[\w.\-]+\.[a-z]{2,})')
POSTAL_RE     = re.compile(r'〒(\d{3}-\d{4})')
LICENSE_RE    = re.compile(r'(東京都知事|大阪府知事|国土交通大臣)[（(]\d+[）)]\s*第\d+号')
SCHOOL_RE     = re.compile(r'(小学校|中学校)\s+(\S+(?:小学校|中学校|学校)?)\s+(徒歩約?\s*\d+\s*分)')
LEASE_PERIOD_RE = re.compile(r'(令和\d+年\d+月\d+日)[～〜](令和\d+年\d+月\d+日)')
GROUND_RENT_RE  = re.compile(r'([\d,]+)円/月')
ELECTRIC_RE   = re.compile(r'(東京電力|関西電力|中部電力|九州電力|東北電力|北海道電力|四国電力|中国電力|沖縄電力|電力)')
GAS_RE        = re.compile(r'(都市ガス|プロパン|個別プロパン|LP[Gg]as|LPガス)')
WATER_RE      = re.compile(r'(公営上下水道|公営水道|私設水道|上下水道)')

# Property type keywords
PROP_TYPES = ['中古戸建', '新築戸建', '中古マンション', '新築マンション', '土地', '店舗', '事務所', '倉庫']


def extract_text(pdf_path: str) -> str:
    """Extract full text from all pages of a PDF."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text


def parse_property(pdf_path: str) -> dict:
    """
    Main parser. Returns a dict with keys matching the HTML form fields.
    """
    text = extract_text(pdf_path)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    result = {}

    # ── Property type ──
    for pt in PROP_TYPES:
        if pt in text:
            result['propertyType'] = pt
            break

    # ── Title / catchphrase (first non-empty line that is a property type) ──
    for line in lines[:5]:
        if any(pt in line for pt in PROP_TYPES):
            result['propertyName'] = line
            break

    # ── Address ──
    # Look for 都道府県 pattern or 区丁目 pattern
    addr_re = re.compile(r'(東京都|大阪府|神奈川県|愛知県|福岡県|埼玉県|千葉県|京都府|兵庫県|北海道|\w+[都道府県])'
                         r'\S+[市区町村]\S+')
    m = addr_re.search(text)
    if m:
        result['address'] = m.group(0)

    # Short address (for header, e.g. "新宿区北新宿３丁目")
    short_addr_re = re.compile(r'([^\s]{2,10}[区市町村]\S+丁目)')
    ms = short_addr_re.search(text)
    if ms and 'address' not in result:
        result['address'] = ms.group(0)

    # ── Price ──
    m = PRICE_RE.search(text)
    if m:
        result['price'] = m.group(1) + '万円'

    # ── Stations ──
    stations = []
    for m in STATION_RE.finditer(text):
        stations.append({
            'line':    m.group(1).strip(),
            'station': m.group(2).strip() + '駅',
            'walk':    m.group(3)
        })
    if stations:
        result['stations'] = stations
    else:
        # Fallback: look for 徒歩X分 near 駅
        st_fallback = re.findall(r'[『「](.{2,10})[』」]駅\s*徒歩\s*(\d+)\s*分', text)
        result['stations'] = [{'line': '', 'station': s+'駅', 'walk': w} for s, w in st_fallback]

    # ── Land ──
    # Area
    land_areas = LAND_AREA_RE.findall(text)
    if land_areas:
        result['landArea'] = land_areas[0]
    tsubo = TSUBO_RE.findall(text)
    if tsubo:
        result['landAreaTsubo'] = tsubo[0]

    # Land right
    if '借地権' in text:
        result['landRight'] = '借地権'
    elif '地上権' in text:
        result['landRight'] = '地上権'
    else:
        result['landRight'] = '所有権'

    # Ground type (地目)
    if '宅地' in text:
        result['landCategory'] = '宅地'

    # Front road
    road_re = re.compile(r'接面道路[：:]\s*(.+)')
    m = road_re.search(text)
    if m:
        result['frontRoad'] = m.group(1).strip()
    elif '建築基準法上の道路に該当しない通路' in text:
        result['frontRoad'] = '建築基準法上の道路に該当しない通路（建築不可）'

    # Rebuild
    if '再建築不可' in text:
        result['rebuild'] = '再建築不可'
    elif '再建築可' in text:
        result['rebuild'] = '再建築可'

    # Lease period
    m = LEASE_PERIOD_RE.search(text)
    if m:
        result['leasePeriod'] = m.group(1) + '〜' + m.group(2)
    m = GROUND_RENT_RE.search(text)
    if m:
        result['groundRent'] = m.group(1) + '円/月'

    # ── Building ──
    # Built year
    built_re = re.compile(r'築年月[：:\s]*([\S]+)')
    m = built_re.search(text)
    if m:
        result['builtYear'] = m.group(1).strip()

    # Structure
    struct_re = re.compile(r'構\s*造[：:\s]*([\S\s]{2,20}?)(?:\n|■)')
    m = struct_re.search(text)
    if m:
        result['structure'] = m.group(1).strip()

    # Floor areas
    floors = FLOOR_RE.findall(text)
    for floor_num, area in floors:
        key = f'floorArea{floor_num}'
        result[key] = f'{floor_num}階 {area}㎡'

    m = TOTAL_FLOOR_RE.search(text)
    if m:
        result['totalFloorArea'] = m.group(1)

    # ── Legal ──
    if '市街化区域' in text:
        result['cityPlan'] = '市街化区域'
    elif '市街化調整区域' in text:
        result['cityPlan'] = '市街化調整区域'

    use_zone_re = re.compile(r'用途地域[：:]\s*([^\n■・]+)')
    m = use_zone_re.search(text)
    if m:
        result['useZone'] = m.group(1).strip()

    if '防火地域' in text and '準' not in text[max(0, text.index('防火地域')-1):text.index('防火地域')]:
        result['fireZone'] = '防火地域'
    elif '準防火地域' in text:
        result['fireZone'] = '準防火地域'

    height_re = re.compile(r'高度地区[：:]\s*([^\n■]+)')
    m = height_re.search(text)
    if m:
        result['heightDistrict'] = m.group(1).strip()

    m = BCR_RE.search(text)
    if m:
        result['bcr'] = m.group(1) + '%'
    m = FAR_RE.search(text)
    if m:
        result['far'] = m.group(1) + '%'

    other_re = re.compile(r'その他[：:]\s*([^\n]+)')
    m = other_re.search(text)
    if m:
        result['otherLegal'] = m.group(1).strip()

    # ── Nearby ──
    result['nearby'] = [
        {'name': n, 'walk': w}
        for n, w in NEARBY_RE.findall(text)
    ]

    # ── Schools ──
    for m in SCHOOL_RE.finditer(text):
        kind, name, dist = m.group(1), m.group(2), m.group(3)
        if kind == '小学校':
            result['elemSchool'] = name
            result['elemSchoolDist'] = dist.strip()
        else:
            result['juniorSchool'] = name
            result['juniorSchoolDist'] = dist.strip()

    # ── Utilities ──
    m = ELECTRIC_RE.search(text)
    if m:
        result['electric'] = m.group(0)
    m = GAS_RE.search(text)
    if m:
        result['gas'] = m.group(0)
    m = WATER_RE.search(text)
    if m:
        result['water'] = m.group(0)

    # Current status
    if '空室' in text:
        result['currentStatus'] = '空室'
    elif '居住中' in text:
        result['currentStatus'] = '居住中'
    elif '賃貸中' in text:
        result['currentStatus'] = '賃貸中'

    # Handover
    handover_re = re.compile(r'引き渡し[：:]\s*([^\n■]+)')
    m = handover_re.search(text)
    if m:
        result['handover'] = m.group(1).strip()

    # ── Remarks ──
    remarks_parts = []
    if '再建築不可' in text:
        remarks_parts.append('■再建築不可')
    note_re = re.compile(r'※([^\n]+)')
    for m in note_re.finditer(text):
        remarks_parts.append('※' + m.group(1).strip())
    result['remarks'] = '\n'.join(remarks_parts)

    # ── Company / Agent ──
    # Company name — prefer 株式会社 / 有限会社 pattern over loose match
    corp_re = re.compile(r'(株式会社[\S]{1,20}|有限会社[\S]{1,20}|合同会社[\S]{1,20}|[\S]{1,10}株式会社)')
    m = corp_re.search(text)
    if m:
        result['companyName'] = m.group(0)

    # Brand
    brand_re = re.compile(r'([\S]+不動産ショップ|[\S]+リアルエステート)')
    m = brand_re.search(text)
    if m:
        result['brandName'] = m.group(0)

    # Address with postal — look for address line AFTER the postal code
    postal_m = POSTAL_RE.search(text)
    if postal_m:
        addr_after_postal = re.search(
            r'〒\d{3}-\d{4}\s*\n?\s*([^\n【】]+[都道府県市区町村]\S+)', text)
        if addr_after_postal:
            result['companyAddress'] = addr_after_postal.group(1).strip()
        else:
            for line in lines:
                if postal_m.group(0) in line:
                    # Strip the postal code from the line for cleaner output
                    result['companyAddress'] = line.replace(postal_m.group(0), '').strip()
                    break

    # License
    m = LICENSE_RE.search(text)
    if m:
        result['licenseNo'] = m.group(0)

    # Agent name
    agent_re = re.compile(r'【担\s*当】\s*(\S+)')
    m = agent_re.search(text)
    if m:
        result['agentName'] = m.group(1).strip()

    m = TEL_RE.search(text)
    if m:
        result['tel'] = m.group(1).strip()
    m = FAX_RE.search(text)
    if m:
        result['fax'] = m.group(1).strip()
    m = EMAIL_RE.search(text)
    if m:
        result['email'] = m.group(1).strip()

    # Transaction type
    if '売主' in text:
        result['transactionType'] = '売主'
    elif '媒介' in text:
        result['transactionType'] = '媒介'

    # Fee
    fee_re = re.compile(r'手\s*数\s*料】\s*(\S+)')
    m = fee_re.search(text)
    if m:
        result['fee'] = m.group(1).strip()

    # Catchcopy (lines containing PR keywords)
    catchcopy_re = re.compile(r'(積極買取中|お気軽にご相談|投資物件|おすすめ|人気エリア)')
    m = catchcopy_re.search(text)
    if m:
        for line in lines:
            if m.group(0) in line:
                result['catchcopy'] = line
                break

    return result


# ── Vercel handler (BaseHTTPRequestHandler) ──────────────────────────────────

import cgi, io, tempfile, os
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        try:
            content_type = self.headers.get('content-type', '')
            content_length = int(self.headers.get('content-length', 0))
            body = self.rfile.read(content_length)

            # Parse multipart/form-data
            ctype, pdict = cgi.parse_header(content_type)
            if ctype != 'multipart/form-data':
                self._send(400, b'Expected multipart/form-data')
                return

            pdict['boundary'] = bytes(pdict['boundary'], 'utf-8')
            pdict['CONTENT-LENGTH'] = content_length
            fields = cgi.parse_multipart(io.BytesIO(body), pdict)

            file_data = fields.get('file', [None])[0]
            if not file_data:
                self._send(400, b'No file field in form data')
                return

            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name

            result = parse_property(tmp_path)
            os.unlink(tmp_path)

            body_out = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self._cors()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body_out)))
            self.end_headers()
            self.wfile.write(body_out)

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


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python parse_pdf.py <path_to_pdf>")
        sys.exit(1)
    result = parse_property(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
