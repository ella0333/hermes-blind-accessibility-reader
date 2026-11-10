"""Local connection between the browser extension and the plugin, on 127.0.0.1 only."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

logger = logging.getLogger("plugin.blind-accessibility-reader")
EXTENSION_ID = "jcimlpiggmhkgionffhamgkkidfcgpif"
ALLOWED_ORIGIN = f"chrome-extension://{EXTENSION_ID}"
DEFAULT_PORT = 47823
MAX_BODY = 12 * 1024 * 1024


def _route(service: Any, path: str, body: dict) -> dict:
    s = service
    if path == "/status":
        s.seen()
        return s.status()
    if path == "/tick":
        return s.tick()
    if path == "/settings":
        msg = s.apply_setting(str(body.get("key")), body.get("value"))
        return {"message": msg, "status": s.status()}
    if path == "/image":
        return s.describe_image(src=str(body.get("src") or ""), image_b64=str(body.get("image") or ""),
                                alt=str(body.get("alt") or ""), reason=str(body.get("reason") or "add"))
    if path == "/price":
        return {"text": s.price_estimate(str(body.get("kind") or "image"), body.get("seconds"))}
    if path == "/video/offer":
        return {"text": s.video_offer(body.get("seconds"))}
    if path == "/video/start":
        return s.narration_start(str(body.get("video")), body.get("seconds"))
    if path == "/video/stop":
        return s.narration_stop(str(body.get("video")))
    if path == "/video/frame":
        return s.frame(str(body.get("video")), str(body.get("image") or ""))
    if path == "/video/single":
        return s.single_frame(str(body.get("image") or ""))
    if path == "/screen":
        return s.screen(str(body.get("image") or ""), str(body.get("question") or ""))
    if path == "/speak":
        return s.speak(str(body.get("text") or ""))
    if path == "/result":
        return s.command_result(str(body.get("id")), str(body.get("text") or ""))
    return {"error": "unknown request"}


class _Handler(BaseHTTPRequestHandler):
    service: Any = None
    port: int = DEFAULT_PORT

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug("blind-accessibility-reader server: " + fmt, *args)

    def _send(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.end_headers()
        self.wfile.write(data)

    def _trusted(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return self.headers.get("Origin") == ALLOWED_ORIGIN and host in ("127.0.0.1", "localhost")

    def do_OPTIONS(self) -> None:
        if not self._trusted():
            self._send(403, {"error": "forbidden"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        self._send(405, {"error": "use POST from the extension"})

    def do_POST(self) -> None:
        if not self._trusted():
            self._send(403, {"error": "forbidden"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._send(413, {"error": "too large"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, _route(self.service, self.path, body if isinstance(body, dict) else {}))
        except Exception as exc:
            logger.exception("blind-accessibility-reader server error")
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"[:300]})


class LocalServer:
    def __init__(self, service: Any, port: int = DEFAULT_PORT):
        self.service = service
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> str:
        """Start listening; returns '' or a sentence explaining why it could not."""
        if self._httpd:
            return ""
        handler = type("Handler", (_Handler,), {"service": self.service, "port": self.port})
        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        except OSError:
            return (f"Port {self.port} is busy, probably another Hermes window already running the reader. "
                    "The extension will use that one.")
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="blind-accessibility-reader-server",
                                        daemon=True)
        self._thread.start()
        return ""

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
