"""
user_profile.py
───────────────
GET  /api/user-profile   → returns Auth0 user_metadata for the calling user
POST /api/user-profile   → updates Auth0 user_metadata for the calling user

Auth:  Authorization: Bearer <access_token>   (issued by auth0-spa-js)
Flow:  token → /userinfo (validate + get sub) → Management API (read/write)
"""

import json, os, urllib.request, urllib.parse, urllib.error
from http.server import BaseHTTPRequestHandler

AUTH0_DOMAIN        = os.environ.get('AUTH0_DOMAIN', '')
AUTH0_CLIENT_ID     = os.environ.get('AUTH0_MGMT_CLIENT_ID', '')   # RWA app — Management API
AUTH0_CLIENT_SECRET = os.environ.get('AUTH0_MGMT_CLIENT_SECRET', '')

# Check required env vars once at module load — surface missing config clearly
_MISSING_ENV = [k for k, v in {
    'AUTH0_DOMAIN': AUTH0_DOMAIN,
    'AUTH0_MGMT_CLIENT_ID': AUTH0_CLIENT_ID,
    'AUTH0_MGMT_CLIENT_SECRET': AUTH0_CLIENT_SECRET,
}.items() if not v]


# ── Auth0 helpers ─────────────────────────────────────────────────────────────

def _userinfo(access_token: str) -> dict:
    """Validate the access token via Auth0 /userinfo and return the user dict."""
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/userinfo',
        headers={'Authorization': f'Bearer {access_token}'},
        method='GET'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _mgmt_token() -> str:
    """Obtain a Management API token via client_credentials grant."""
    payload = json.dumps({
        'client_id':     AUTH0_CLIENT_ID,
        'client_secret': AUTH0_CLIENT_SECRET,
        'audience':      f'https://{AUTH0_DOMAIN}/api/v2/',
        'grant_type':    'client_credentials',
    }).encode()
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/oauth/token',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())['access_token']


def _get_metadata(user_id: str, mgmt_tok: str) -> dict:
    uid = urllib.parse.quote(user_id, safe='')
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/api/v2/users/{uid}',
        headers={'Authorization': f'Bearer {mgmt_tok}'},
        method='GET'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read()).get('user_metadata', {})


def _set_metadata(user_id: str, metadata: dict, mgmt_tok: str) -> None:
    uid = urllib.parse.quote(user_id, safe='')
    payload = json.dumps({'user_metadata': metadata}).encode()
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/api/v2/users/{uid}',
        data=payload,
        headers={
            'Authorization':  f'Bearer {mgmt_tok}',
            'Content-Type':   'application/json',
        },
        method='PATCH'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        r.read()


# ── Handler ───────────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass   # silence Vercel access log

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def _send(self, status: int, body: dict):
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
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _check_env(self):
        """Return True if OK, else send 503 with which env vars are missing."""
        if _MISSING_ENV:
            self._send(503, {'error': f'Server misconfigured — missing env vars: {", ".join(_MISSING_ENV)}'})
            return False
        return True

    def do_GET(self):
        if not self._check_env(): return
        tok = self._token()
        if not tok:
            return self._send(401, {'error': 'Missing token'})
        try:
            user    = _userinfo(tok)
            sub     = user.get('sub')
            if not sub:
                return self._send(400, {'error': 'No sub in token'})
            mgmt    = _mgmt_token()
            meta    = _get_metadata(sub, mgmt)
            self._send(200, meta)
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            self._send(e.code, {'error': e.reason, 'detail': body})
        except Exception as e:
            self._send(500, {'error': str(e)})

    def do_POST(self):
        if not self._check_env(): return
        tok = self._token()
        if not tok:
            return self._send(401, {'error': 'Missing token'})
        try:
            user    = _userinfo(tok)
            sub     = user.get('sub')
            if not sub:
                return self._send(400, {'error': 'No sub in token'})
            length  = int(self.headers.get('Content-Length', 0))
            body    = json.loads(self.rfile.read(length))
            mgmt    = _mgmt_token()
            _set_metadata(sub, body, mgmt)
            self._send(200, {'ok': True})
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            self._send(e.code, {'error': e.reason, 'detail': body})
        except Exception as e:
            self._send(500, {'error': str(e)})
