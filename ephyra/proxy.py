"""Local HTTP proxy between GStreamer and the server (docs/playback.md).

GStreamer's HTTP sources and its HLS downloader can't present a client
certificate, and the access token should not sit in URLs. The player
therefore opens http://127.0.0.1:<port>/<secret>/<path>; this proxy
forwards the request to the current server address (local or remote)
with the Authorization header and the client certificate, and streams
the answer back. Range requests pass through, so seeking works.
No GTK."""
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from gi.repository import GLib

from ephyra.http import HttpError

log = logging.getLogger("ephyra.proxy")

CHUNK = 64 * 1024
FORWARD_REQUEST = ("Range", "If-Range", "Accept")
FORWARD_RESPONSE = ("Content-Type", "Content-Length", "Content-Range",
                    "Accept-Ranges", "Last-Modified", "ETag")


class MediaProxy:
    def __init__(self, jellyfin):
        self.jellyfin = jellyfin
        self.secret = secrets.token_urlsafe(24)
        self._server = None

    def start(self):
        if self._server:
            return
        proxy = self

        class Handler(_Handler):
            owner = proxy

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True,
                         name="ephyra-proxy").start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def url(self, path):
        """Local URL for a server path like "/Videos/<id>/stream?…"."""
        self.start()
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}/{self.secret}{path}"


class _Handler(BaseHTTPRequestHandler):
    owner = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def do_HEAD(self):
        self._forward("HEAD")

    def do_GET(self):
        self._forward("GET")

    def _forward(self, method):
        prefix = f"/{self.owner.secret}/"
        if not self.path.startswith(prefix):
            self.send_error(404)
            return
        jellyfin = self.owner.jellyfin
        url = jellyfin.base_url + self.path[len(prefix) - 1:]
        # identity: libsoup would decode a compressed body, which would
        # then no longer match the Content-Length passed on.
        headers = {"Authorization": jellyfin.authorization(),
                   "Accept-Encoding": "identity"}
        for name in FORWARD_REQUEST:
            if self.headers.get(name):
                headers[name] = self.headers[name]
        try:
            status, upstream, stream = jellyfin.http.open(method, url, headers)
        except HttpError as e:
            log.info("proxy: %s", e)
            self.send_error(502, str(e))
            return
        self.send_response(status)
        length_known = False
        for name in FORWARD_RESPONSE:
            value = _get(upstream, name)
            if value is not None:
                self.send_header(name, value)
                length_known |= name == "Content-Length"
        if not length_known:
            # Unknown length (live transcode): end the body by closing.
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if method == "HEAD":
            stream.close(None)
            return
        try:
            while True:
                data = stream.read_bytes(CHUNK, None).get_data()
                if not data:
                    break
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the player seeked or stopped
        except GLib.Error as e:
            log.info("proxy: upstream: %s", e.message)
            self.close_connection = True
        finally:
            try:
                stream.close(None)
            except GLib.Error:
                pass


def _get(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None
