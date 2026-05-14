"""
monospages-admin.py
───────────────────
Handles monospages role management via Auth0 app_metadata.

GET  /api/monospages-admin
    No params  → return current user's monospages_role (used by all pages)
    ?action=list_users → return ALL users with their role (admin only)

POST /api/monospages-admin
    Body: { "target_user_id": "<auth0|xxx>", "role": "worker" }
    → update target user's app_metadata.monospages_role (admin only)

Auth: Authorization: Bearer <access_token>
Env:  AUTH0_DOMAIN, AUTH0_MGMT_CLIENT_ID, AUTH0_MGMT_CLIENT_SECRET
"""

import json, os, urllib.request, urllib.parse, urllib.error
from http.server import BaseHTTPRequestHandler

AUTH0_DOMAIN   = os.environ.get('AUTH0_DOMAIN', '')
MGMT_CLIENT_ID = os.environ.get('AUTH0_MGMT_CLIENT_ID', '')
MGMT_SECRET    = os.environ.get('AUTH0_MGMT_CLIENT_SECRET', '')

VALID_ROLES = ('viewer_basic', 'viewer_premium', 'worker', 'admin')

_MISSING_ENV = [k for k, v in {
    'AUTH0_DOMAIN': AUTH0_DOMAIN,
    'AUTH0_MGMT_CLIENT_ID': MGMT_CLIENT_ID,
    'AUTH0_MGMT_CLIENT_SECRET': MGMT_SECRET,
}.items() if not v]


# ── Auth0 helpers ─────────────────────────────────────────────────────────────

def _userinfo(tok: str) -> dict:
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/userinfo',
        headers={'Authorization': f'Bearer {tok}'}, method='GET'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _mgmt_token() -> str:
    payload = json.dumps({
        'client_id': MGMT_CLIENT_ID,
        'client_secret': MGMT_SECRET,
        'audience': f'https://{AUTH0_DOMAIN}/api/v2/',
        'grant_type': 'client_credentials',
    }).encode()
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/oauth/token',
        data=payload, headers={'Content-Type': 'application/json'}, method='POST'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())['access_token']


def _get_app_metadata(user_id: str, mgmt_tok: str) -> dict:
    uid = urllib.parse.quote(user_id, safe='')
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/api/v2/users/{uid}?fields=app_metadata',
        headers={'Authorization': f'Bearer {mgmt_tok}'}, method='GET'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read()).get('app_metadata', {})


def _set_app_metadata(user_id: str, meta: dict, mgmt_tok: str) -> None:
    uid = urllib.parse.quote(user_id, safe='')
    payload = json.dumps({'app_metadata': meta}).encode()
    req = urllib.request.Request(
        f'https://{AUTH0_DOMAIN}/api/v2/users/{uid}',
        data=payload,
        headers={'Authorization': f'Bearer {mgmt_tok}', 'Content-Type': 'application/json'},
        method='PATCH'
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        r.read()


def _list_users(mgmt_tok: str) -> list:
    """Return all users with their monospages_role. Pages through Auth0 (max 1000)."""
    users = []
    page, per_page = 0, 50
    while True:
        url = (f'https://{AUTH0_DOMAIN}/api/v2/users'
               f'?per_page={per_page}&page={page}'
               f'&fields=user_id,email,name,picture,app_metadata,last_login'
               f'&include_fields=true')
        req = urllib.request.Request(
            url, headers={'Authorization': f'Bearer {mgmt_tok}'}, method='GET'
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            batch = json.loads(r.read())
        if not batch:
            break
        for u in batch:
            meta = u.get('app_metadata') or {}
            users.append({
                'user_id':    u.get('user_id', ''),
                'email':      u.get('email', ''),
                'name':       u.get('name', ''),
                'picture':    u.get('picture', ''),
                'last_login': u.get('last_login', ''),
                'monospages_role': meta.get('monospages_role', ''),
            })
        if len(batch) < per_page:
            break
        page += 1
    return users


# ── Handler ───────────────────────────────────────────────────────────────────

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

    def _check_env(self):
        if _MISSING_ENV:
            self._send(503, {'error': f'Missing env vars: {", ".join(_MISSING_ENV)}'})
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

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
            my_meta = _get_app_metadata(sub, mgmt)
            my_role = my_meta.get('monospages_role', '')

            # Parse query string
            qs     = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            action = qs.get('action', [None])[0]

            if action == 'list_users':
                # Admin only
                if my_role != 'admin':
                    return self._send(403, {'error': 'Admin role required'})
                users = _list_users(mgmt)
                return self._send(200, {'users': users})

            # Default: return current user's role
            self._send(200, {
                'monospages_role': my_role,
                'email': user.get('email', ''),
                'name':  user.get('name', ''),
            })

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
            mgmt    = _mgmt_token()
            my_meta = _get_app_metadata(sub, mgmt)
            my_role = my_meta.get('monospages_role', '')

            # Only admin can update roles
            if my_role != 'admin':
                return self._send(403, {'error': 'Admin role required'})

            length = int(self.headers.get('Content-Length', 0))
            body   = json.loads(self.rfile.read(length))
            target_id = body.get('target_user_id', '').strip()
            new_role  = body.get('role', '').strip()

            if not target_id:
                return self._send(400, {'error': 'target_user_id required'})
            if new_role not in VALID_ROLES and new_role != '':
                return self._send(400, {'error': f'Invalid role. Must be one of: {", ".join(VALID_ROLES)}'})

            # Get current app_metadata (to preserve other keys), then patch role
            target_meta = _get_app_metadata(target_id, mgmt)
            if new_role:
                target_meta['monospages_role'] = new_role
            else:
                target_meta.pop('monospages_role', None)   # '' = remove role
            _set_app_metadata(target_id, target_meta, mgmt)
            self._send(200, {'ok': True, 'user_id': target_id, 'role': new_role})

        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            self._send(e.code, {'error': e.reason, 'detail': body})
        except Exception as e:
            self._send(500, {'error': str(e)})
