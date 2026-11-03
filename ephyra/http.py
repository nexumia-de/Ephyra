"""HTTP with libsoup 3 from worker threads, with an optional client
certificate. Every thread gets its own SoupSession, so connections are
reused within a thread and no session is shared between threads.
No GTK."""
import threading

import gi

gi.require_version("Soup", "3.0")
from gi.repository import Gio, GLib, Soup  # noqa: E402

from ephyra import USER_AGENT  # noqa: E402

NETWORK = "network"          # no route, DNS, refused, timeout
TLS = "tls"                  # handshake failed, untrusted server
CERTIFICATE_REQUIRED = "certificate-required"
AUTH = "auth"                # 401
SERVER = "server"            # other HTTP errors


class HttpError(Exception):
    def __init__(self, kind, message, status=0):
        super().__init__(message)
        self.kind = kind
        self.status = status


def classify(error):
    """HttpError for a GLib.Error from libsoup or GIO."""
    text = (error.message or "").lower()
    # With TLS 1.3 the server rejects a missing certificate after the
    # handshake, which GnuTLS reports as a received alert, not as
    # CERTIFICATE_REQUIRED.
    if error.matches(Gio.tls_error_quark(), Gio.TlsError.CERTIFICATE_REQUIRED) \
            or "certificate is required" in text:
        return HttpError(CERTIFICATE_REQUIRED,
                         "The server asks for a client certificate")
    if error.domain == GLib.quark_to_string(Gio.tls_error_quark()):
        return HttpError(TLS, f"Secure connection failed: {error.message}")
    # GnuTLS reports a rejected client certificate as a generic alert.
    if "certificate" in text or "tls" in text or "handshake" in text:
        return HttpError(TLS, f"Secure connection failed: {error.message}")
    return HttpError(NETWORK, error.message or "Network error")


def is_certificate_page(body):
    """nginx answers a missing client certificate with HTTP 400 "No
    required SSL certificate was sent" (TLS 1.3 completes the handshake
    first); other proxies use similar pages."""
    text = (body or b"")[:2000].lower()
    return b"ssl certificate" in text or b"client certificate" in text


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body


class Client:
    def __init__(self):
        self._local = threading.local()
        # Read by every thread, replaced by the main thread.
        self.certificate = None
        # Trusted CAs for the server certificate; None is the system's.
        # Tests set their own CA here.
        self.tls_database = None

    def _session(self):
        session = getattr(self._local, "session", None)
        if session is None:
            session = Soup.Session(user_agent=USER_AGENT, timeout=30,
                                   max_conns_per_host=4)
            if self.tls_database is not None:
                session.set_tls_database(self.tls_database)
            self._local.session = session
        return session

    def _message(self, method, url, headers, body, content_type):
        try:
            msg = Soup.Message.new(method, url)
        except TypeError:
            msg = None
        if msg is None:
            raise HttpError(NETWORK, f"Invalid address {url}")
        for name, value in (headers or {}).items():
            msg.props.request_headers.replace(name, value)
        if body is not None:
            msg.set_request_body_from_bytes(content_type,
                                            GLib.Bytes.new(body))
        # Without a certificate libsoup fails the handshake with
        # CERTIFICATE_REQUIRED when the server asks for one, which the
        # setup page turns into "choose your client certificate".
        if self.certificate is not None:
            msg.set_tls_client_certificate(self.certificate)
        return msg

    def request(self, method, url, headers=None, body=None,
                content_type="application/json", timeout=None):
        """Blocking request in the calling (worker) thread."""
        session = self._session()
        if timeout is not None:
            session.props.timeout = timeout
        msg = self._message(method, url, headers, body, content_type)
        try:
            data = session.send_and_read(msg, None)
        except GLib.Error as e:
            raise classify(e) from None
        finally:
            if timeout is not None:
                session.props.timeout = 30
        status = msg.get_status()
        response = Response(status, _headers(msg.props.response_headers),
                            data.get_data() or b"")
        if status in (400, 403) and is_certificate_page(response.body):
            raise HttpError(CERTIFICATE_REQUIRED,
                            "The server asks for a client certificate", status)
        if status == 401:
            raise HttpError(AUTH, "Signed out by the server", status)
        if status >= 400:
            raise HttpError(SERVER, f"Server error {status}", status)
        return response

    def open(self, method, url, headers=None):
        """Blocking request that returns (status, headers, input stream)
        before the body is read, for the media proxy."""
        session = self._session()
        msg = self._message(method, url, headers, None, None)
        try:
            stream = session.send(msg, None)
        except GLib.Error as e:
            raise classify(e) from None
        return msg.get_status(), _headers(msg.props.response_headers), stream


def _headers(soup_headers):
    out = {}
    soup_headers.foreach(lambda name, value: out.__setitem__(name, value))
    return out
