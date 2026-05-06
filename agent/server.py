"""
VOLTCORE API Server v1.0
=========================
Serves simulation state to the dashboard via HTTP.
Runs alongside simulate.py.

Usage:
  Terminal 1: python3 agent/simulate.py --fast
  Terminal 2: python3 agent/server.py
  Browser:    open dashboard.html (or http://localhost:8080)
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

STATE_FILE = Path("agent/simulation_state.json")
PORT       = 8090


class VoltcoreHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Suppress access logs

    def do_GET(self):
        # CORS headers for dashboard
        if self.path == "/state":
            self._serve_state()
        elif self.path == "/health":
            self._serve_json({"status": "ok", "service": "voltcore-api"})
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_state(self):
        try:
            if STATE_FILE.exists():
                data = STATE_FILE.read_text()
                self._serve_raw_json(data)
            else:
                self._serve_json({"error": "No simulation state yet — run simulate.py first"})
        except Exception as e:
            self._serve_json({"error": str(e)})

    def _serve_json(self, obj: dict):
        self._serve_raw_json(json.dumps(obj))

    def _serve_raw_json(self, raw: str):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw.encode())


def run():
    server = HTTPServer(("0.0.0.0", PORT), VoltcoreHandler)
    print(f"\n  ⚡ VOLTCORE API Server")
    print(f"  Listening on http://localhost:{PORT}")
    print(f"  State endpoint: http://localhost:{PORT}/state")
    print(f"  Health check:   http://localhost:{PORT}/health")
    print(f"\n  Start simulation: python3 agent/simulate.py --fast")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    run()
