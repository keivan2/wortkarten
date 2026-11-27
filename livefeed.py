"""Live camera view in the browser: http://<pi-address>:<WK_LIVE_PORT>/

Runs inside the app (the app holds the camera, so nothing else can open it). It serves an
MJPEG stream, which every browser shows as a moving picture. There is no password: anyone on
your home network can open it, so only turn it on if that's fine for you.
"""
import logging
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)

PAGE = b"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Wortkarten Kamera</title>
<style>
  body { margin: 0; background: #111; color: #aaa; font: 14px sans-serif; text-align: center; }
  img { display: block; margin: 0 auto; max-width: 100%; max-height: 94vh; }
</style></head>
<body><img src="/stream" alt="Kamera">
<p>Rot = Erkennungszone &middot; <a href="/snapshot.jpg" style="color:#aaa">Einzelbild</a></p>
</body></html>"""


def start(get_frame: Callable[[], bytes], port: int, fps: float = 4.0) -> None:
    """Serve the live view in a background thread. get_frame returns one JPEG."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the journal quiet
            pass

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(PAGE, "text/html; charset=utf-8")
            elif self.path == "/snapshot.jpg":
                self._send(get_frame(), "image/jpeg")
            elif self.path == "/stream":
                self._stream()
            else:
                self.send_error(404)

        def _stream(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            log.info("Live view opened from %s", self.client_address[0])
            try:
                while True:
                    jpeg = get_frame()
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                     b"Content-Length: %d\r\n\r\n" % len(jpeg))
                    self.wfile.write(jpeg + b"\r\n")
                    time.sleep(1 / fps)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser tab was closed
            except Exception:
                log.exception("Live view stopped")
            log.info("Live view closed from %s", self.client_address[0])

    server = ThreadingHTTPServer(("", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="livefeed", daemon=True).start()
    log.info("Live view on port %d: open http://<pi-address>:%d/", port, port)
