"""
Upload media for monospages field investigation.
Proxies validated payloads to Apps Script.
"""

import base64
import cgi
from http.server import BaseHTTPRequestHandler

from monospages_common import (
    call_apps_script,
    handle_options,
    require_user,
    send_json,
)


class handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_OPTIONS(self):
        handle_options(self)

    def do_POST(self):
        user = require_user(self, write_roles=("worker", "admin"))
        if not user:
            return
        try:
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                return send_json(
                    self, 400, {"error": "multipart/form-data content-type required"}
                )

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": ctype,
                },
            )

            batch_id = (form.getfirst("batch_id", "") or "").strip()
            prop_id = (form.getfirst("prop_id", "") or "").strip()
            if not batch_id or not prop_id:
                return send_json(self, 400, {"error": "batch_id and prop_id required"})

            file_item = form["file"] if "file" in form else None
            if not file_item:
                return send_json(self, 400, {"error": "file is required"})
            if isinstance(file_item, list):
                file_item = file_item[0]
            if not getattr(file_item, "file", None):
                return send_json(self, 400, {"error": "invalid file field"})

            raw = file_item.file.read()
            if not raw:
                return send_json(self, 400, {"error": "empty file"})
            if len(raw) > 15 * 1024 * 1024:
                return send_json(self, 413, {"error": "file exceeds 15MB limit"})

            filename = (file_item.filename or "upload.bin").strip() or "upload.bin"
            mime_type = (getattr(file_item, "type", "") or "application/octet-stream").strip()

            app_resp = call_apps_script(
                "upload_media",
                {
                    "batch_id": batch_id,
                    "prop_id": prop_id,
                    "filename": filename,
                    "mime_type": mime_type,
                    "content_base64": base64.b64encode(raw).decode("ascii"),
                    "uploaded_by": user.get("email", ""),
                    "uploaded_sub": user.get("sub", ""),
                },
            )
            if not app_resp.get("ok", True):
                return send_json(self, 502, {"error": app_resp.get("error", "upload failed")})

            media_item = app_resp.get("media_item") or {}
            if not media_item and app_resp.get("url"):
                media_item = {
                    "url": app_resp.get("url"),
                    "name": filename,
                    "mime_type": mime_type,
                }
            return send_json(self, 200, {"ok": True, "media_item": media_item})
        except Exception as e:
            return send_json(self, 500, {"error": str(e)})
