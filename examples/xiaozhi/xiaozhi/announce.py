"""让任务看板把一句报到音箱上。只在容器网络里听，不对外发布。"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8791


def start_announce_server(app, port=PORT):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print("announce " + (fmt % args), flush=True)

        def _send(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/health":
                self._send(404, {"error": "not found"})
                return
            self._send(200, {"ok": True})

        def do_POST(self):
            if self.path != "/speak":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length > 4000:
                self._send(400, {"error": "too large"})
                return
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"error": "bad json"})
                return
            text = str(payload.get("text", "")).strip()
            if not text or len(text) > 200:
                self._send(400, {"error": "text required"})
                return
            if not lock.acquire(blocking=False):
                self._send(409, {"error": "busy"})
                return
            try:
                future = asyncio.run_coroutine_threadsafe(app.announce(text), app.loop)
                future.result(timeout=50)
            except Exception as exc:
                self._send(502, {"error": str(exc)})
                return
            finally:
                lock.release()
            self._send(200, {"ok": True})

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"announce listening on {port}", flush=True)
