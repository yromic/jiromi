"""Small optional HTTP health server for Render Web Services.

The Discord bot remains the asyncio application. This server runs in its own
thread and only exposes liveness/readiness information; it does not touch the
Discord client or SQLite connection from the HTTP thread.
"""

from __future__ import annotations

import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path == "/live":
            self._respond(HTTPStatus.OK, b"ok\n")
            return

        if self.path == "/health":
            ready = self.server.ready_event.is_set()
            status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
            body = b"ready\n" if ready else b"starting\n"
            self._respond(status, body)
            return

        self._respond(HTTPStatus.NOT_FOUND, b"not found\n")

    def _respond(self, status: HTTPStatus, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        # Render already captures process logs; avoid noisy access logs.
        return


class HealthServer:
    def __init__(self, ready_event: threading.Event):
        self.ready_event = ready_event
        self._server = None
        self._thread = None

    @property
    def enabled(self) -> bool:
        return bool(os.getenv("PORT"))

    def start(self):
        if not self.enabled:
            return

        port = int(os.environ["PORT"])
        self._server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
        self._server.ready_event = self.ready_event
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="render-health-server",
            daemon=True,
        )
        self._thread.start()
        print(f"[HEALTH] HTTP server listening on 0.0.0.0:{port}")

    def stop(self):
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None
        print("[HEALTH] HTTP server stopped")
