"""
Common helpers for monospages APIs.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
MGMT_CLIENT_ID = os.environ.get("AUTH0_MGMT_CLIENT_ID", "")
MGMT_SECRET = os.environ.get("AUTH0_MGMT_CLIENT_SECRET", "")

APPS_SCRIPT_URL = os.environ.get("MONOSPAGES_APPS_SCRIPT_URL", "")
APPS_SCRIPT_SECRET = os.environ.get("MONOSPAGES_APPS_SCRIPT_SECRET", "")

_CACHED_MGMT_TOKEN = {"token": "", "exp": 0}


def _send(handler, status, body):
    data = json.dumps(body, ensure_ascii=False).encode()
    handler.send_response(status)
    _cors(handler)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _cors(handler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


def handle_options(handler):
    handler.send_response(204)
    _cors(handler)
    handler.end_headers()


def _extract_token(handler):
    auth = handler.headers.get("Authorization", "")
    return auth[7:].strip() if auth.startswith("Bearer ") else None


def _userinfo(access_token):
    req = urllib.request.Request(
        f"https://{AUTH0_DOMAIN}/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read())


def _mgmt_token():
    now = int(time.time())
    if _CACHED_MGMT_TOKEN["token"] and _CACHED_MGMT_TOKEN["exp"] - 30 > now:
        return _CACHED_MGMT_TOKEN["token"]

    payload = json.dumps(
        {
            "client_id": MGMT_CLIENT_ID,
            "client_secret": MGMT_SECRET,
            "audience": f"https://{AUTH0_DOMAIN}/api/v2/",
            "grant_type": "client_credentials",
        }
    ).encode()
    req = urllib.request.Request(
        f"https://{AUTH0_DOMAIN}/oauth/token",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        body = json.loads(res.read())
        tok = body["access_token"]
        exp = int(body.get("expires_in", 3600)) + now
        _CACHED_MGMT_TOKEN["token"] = tok
        _CACHED_MGMT_TOKEN["exp"] = exp
        return tok


def _role_for_sub(sub, mgmt_tok):
    uid = urllib.parse.quote(sub, safe="")
    req = urllib.request.Request(
        f"https://{AUTH0_DOMAIN}/api/v2/users/{uid}?fields=app_metadata,email,name",
        headers={"Authorization": f"Bearer {mgmt_tok}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        body = json.loads(res.read())
    role = (body.get("app_metadata") or {}).get("monospages_role", "")
    return {
        "role": role,
        "email": body.get("email", ""),
        "name": body.get("name", ""),
    }


def require_user(handler, write_roles=None):
    missing = []
    for key, val in {
        "AUTH0_DOMAIN": AUTH0_DOMAIN,
        "AUTH0_MGMT_CLIENT_ID": MGMT_CLIENT_ID,
        "AUTH0_MGMT_CLIENT_SECRET": MGMT_SECRET,
    }.items():
        if not val:
            missing.append(key)
    if missing:
        _send(handler, 503, {"error": f"Missing env vars: {', '.join(missing)}"})
        return None

    tok = _extract_token(handler)
    if not tok:
        _send(handler, 401, {"error": "Missing token"})
        return None
    try:
        profile = _userinfo(tok)
        sub = profile.get("sub")
        if not sub:
            _send(handler, 400, {"error": "No sub in token"})
            return None
        mgmt = _mgmt_token()
        role_data = _role_for_sub(sub, mgmt)
        role = role_data["role"] or "viewer_basic"
        if write_roles and role not in write_roles:
            _send(handler, 403, {"error": "Insufficient role"})
            return None
        return {
            "sub": sub,
            "email": profile.get("email", "") or role_data["email"],
            "name": profile.get("name", "") or role_data["name"],
            "role": role,
        }
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        _send(handler, e.code, {"error": e.reason, "detail": detail})
        return None
    except Exception as e:
        _send(handler, 500, {"error": str(e)})
        return None


def parse_json_body(handler):
    raw_len = handler.headers.get("Content-Length", "0").strip()
    length = int(raw_len) if raw_len.isdigit() else 0
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    if not raw:
        return {}
    return json.loads(raw)


def call_apps_script(action, payload):
    if not APPS_SCRIPT_URL:
        raise RuntimeError("MONOSPAGES_APPS_SCRIPT_URL is not set")
    req_payload = dict(payload or {})
    req_payload["action"] = action
    data = json.dumps(req_payload, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json"}
    if APPS_SCRIPT_SECRET:
        headers["X-Monospages-Secret"] = APPS_SCRIPT_SECRET
    req = urllib.request.Request(
        APPS_SCRIPT_URL, data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        body = json.loads(res.read())
    if not isinstance(body, dict):
        raise RuntimeError("Apps Script returned non-JSON object")
    return body


def send_json(handler, status, body):
    _send(handler, status, body)
