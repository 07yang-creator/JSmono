"""
Read/write field-investigation records for a property.
"""

import urllib.parse
from http.server import BaseHTTPRequestHandler

from monospages_common import (
    call_apps_script,
    handle_options,
    parse_json_body,
    require_user,
    send_json,
)


class handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_OPTIONS(self):
        handle_options(self)

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        if user["role"] == "viewer_basic":
            return send_json(self, 403, {"error": "viewer_basic cannot access field records"})
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            batch_id = (qs.get("batch_id", [""])[0] or "").strip()
            prop_id = (qs.get("prop_id", [""])[0] or "").strip()
            if not batch_id or not prop_id:
                return send_json(self, 400, {"error": "batch_id and prop_id required"})
            app_resp = call_apps_script(
                "get_field_record", {"batch_id": batch_id, "prop_id": prop_id}
            )
            if not app_resp.get("ok", True):
                return send_json(self, 502, {"error": app_resp.get("error", "load failed")})
            record = app_resp.get("record") or {
                "batch_id": batch_id,
                "prop_id": prop_id,
                "fields": {},
                "media_items": [],
            }
            return send_json(self, 200, {"ok": True, "record": record})
        except Exception as e:
            return send_json(self, 500, {"error": str(e)})

    def do_POST(self):
        user = require_user(self, write_roles=("worker", "admin"))
        if not user:
            return
        try:
            body = parse_json_body(self)
            batch_id = (body.get("batch_id", "") or "").strip()
            prop_id = (body.get("prop_id", "") or "").strip()
            fields = body.get("fields", {})
            media_items = body.get("media_items", [])
            if not batch_id or not prop_id:
                return send_json(self, 400, {"error": "batch_id and prop_id required"})
            if not isinstance(fields, dict):
                return send_json(self, 400, {"error": "fields must be object"})
            if not isinstance(media_items, list):
                return send_json(self, 400, {"error": "media_items must be array"})

            app_resp = call_apps_script(
                "upsert_field_record",
                {
                    "batch_id": batch_id,
                    "prop_id": prop_id,
                    "fields": fields,
                    "media_items": media_items,
                    "updated_by": user.get("email", ""),
                    "updated_sub": user.get("sub", ""),
                },
            )
            if not app_resp.get("ok", True):
                return send_json(self, 502, {"error": app_resp.get("error", "save failed")})
            return send_json(self, 200, {"ok": True, "record": app_resp.get("record", {})})
        except Exception as e:
            return send_json(self, 500, {"error": str(e)})
