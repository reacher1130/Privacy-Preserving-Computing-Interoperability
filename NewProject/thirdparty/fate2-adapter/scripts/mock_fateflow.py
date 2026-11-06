#!/usr/bin/env python3
"""A tiny mock FATE-Flow 2.x BFIA scheduler for adapter testing."""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

CALLS = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[MOCK]", fmt % args)

    def _json(self, code, msg, data=None):
        body = json.dumps({"code": code, "msg": msg, "data": data or {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(length).decode()
        CALLS.append(("POST", self.path, payload))
        parsed = urlparse(self.path)
        if parsed.path == "/schedule/job/create_all":
            req = json.loads(payload)
            job_id = req.get("job_id", "unknown")
            self._json(0, "create ok", {"job_id": job_id})
        elif parsed.path == "/schedule/job/start":
            self._json(0, "start ok", {})
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        CALLS.append(("GET", self.path, ""))
        parsed = urlparse(self.path)
        if parsed.path == "/schedule/job/status_all":
            qs = parse_qs(parsed.query)
            job_id = qs.get("job_id", ["unknown"])[0]
            # First few calls return RUNNING, then SUCCESS.
            status = "SUCCESS" if len(CALLS) > 6 else "RUNNING"
            self._json(0, "status ok", {job_id: status})
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9380
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[MOCK] FATE-Flow listening on http://127.0.0.1:{port}")
    server.serve_forever()
