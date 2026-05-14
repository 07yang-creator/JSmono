"""
monospages-config.py
────────────────────
GET  /api/monospages-config?section=banner  → return banner config JSON
POST /api/monospages-config                 → save config (admin only)
     Body: { "section": "banner", "data": { ...fields... } }

Persistence: config is stored as a JSON string in the Vercel environment
variable MONOSPAGES_CONFIG. On first deploy this will be empty; the admin
page writes to it via the Vercel API — or alternatively, store in a
Google Sheet tab called "config" with columns: section | key | value.

For the demo, values are returned from MONOSPAGES_CONFIG env var (JSON).
If not set, sensible defaults are returned.

Auth: Authorization: Bearer <access_token>  (required for POST)
Env:  AUTH0_DOMAIN, AUTH0_MGMT_CLIENT_ID, AUTH0_MGMT_CLIENT_SECRET,
      MONOSPAGES_CONFIG (optional JSON blob — updated via Vercel dashboard)
"""

import json, os, urllib.request, urllib.parse, urllib.error
from http.server import BaseHTTPRequestHandler

AUTH0_DOMAIN   = os.environ.get('AUTH0_DOMAIN', '')
MGMT_CLIENT_ID = os.environ.get('AUTH0_MGMT_CLIENT_ID', '')
MGMT_SECRET    = os.environ.get('AUTH0_MGMT_CLIENT_SECRET', '')

DEFAULTS = {
    'banner': {
        'tag':       '最新公告',
        'title':     '2026年5月A批次开始受理',
        'desc':      '本期共收录21件东京都内法拍物件。\n入札期间：2026年5月21日 — 5月28日，开札日：6月3日。',
        'cta_text':  '查看本批次物件 →',
        'cta_href':  '/monospages/2026-5a/',
        'stat1_num': '21',
        'stat2_num': '5/28',
        'bg_image':  'https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=1600&q=80&auto=format&fit=crop',
    }
}

# In-memory store (resets on cold start — acceptable for low-frequency config writes)
# For production, replace with Vercel KV or a Google Sheet config tab.
_CONFIG: dict = {}

def _load_env_config():
    """Load initial config from MONOSPAGES_CONFIG env var (JSON string)."""
    raw = os.environ.get('MONOSPAGES_CONFIG', '')
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}

_CONFIG = _load_env_config()


def _userinfo(tok: str) -> dict:
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/userinfo',
        headers={'Authorization': f'Bearer {tok}'}, method='GET'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _mgmt_token() -> str:
    payload = json.dumps({
        'client_id': MGMT_CLIENT_ID, 'client_secret': MGMT_SECRET,
        'audience': f'https://{AUTH0_DOMAIN}/api/v2/',
        'grant_type': 'client_credentials',
    }).encode()
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/oauth/token',
        data=payload, headers={'Content-Type': 'application/json'}, method='POST'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())['access_token']


def _get_role(sub: str, mgmt_tok: str) -> str:
    uid = urllib.parse.quote(sub, safe='')
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/api/v2/users/{uid}?fields=app_metadata',
        headers={'Authorization': f'Bearer {mgmt_tok}'}, method='GET'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read()).get('app_metadata', {}).get('monospages_role', '')


class handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def _send(self, status: int, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _token(self):
        auth = self.headers.get('Authorization', '')
        return auth[7:].strip() if auth.startswith('Bearer ') else None

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        qs      = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        section = qs.get('section', [None])[0]
        if not section:
            return self._send(400, {'error': 'section param required'})
        # Return stored config, falling back to defaults
        cfg = {**DEFAULTS.get(section, {}), **_CONFIG.get(section, {})}
        self._send(200 if cfg else 404, cfg or {'error': f'No config for section: {section}'})

    def do_POST(self):
        tok = self._token()
        if not tok:
            return self._send(401, {'error': 'Missing token'})
        if not all([AUTH0_DOMAIN, MGMT_CLIENT_ID, MGMT_SECRET]):
            return self._send(503, {'error': 'Auth env vars not configured'})
        try:
            user = _userinfo(tok)
            sub  = user.get('sub')
            if not sub:
                return self._send(400, {'error': 'No sub in token'})
            mgmt = _mgmt_token()
            role = _get_role(sub, mgmt)
            if role != 'admin':
                return self._send(403, {'error': 'Admin role required'})

            length  = int(self.headers.get('Content-Length', 0))
            body    = json.loads(self.rfile.read(length))
            section = body.get('section', '')
            data    = body.get('data', {})
            if not section or not isinstance(data, dict):
                return self._send(400, {'error': 'section and data required'})

            _CONFIG[section] = data
            # TODO: persist to Vercel KV or Google Sheet config tab for
            #       durability across cold starts. For now, in-memory only.
            self._send(200, {'ok': True, 'section': section})

        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            self._send(e.code, {'error': e.reason, 'detail': body})
        except Exception as e:
            self._send(500, {'error': str(e)})
