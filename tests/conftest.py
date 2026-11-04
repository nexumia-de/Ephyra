"""Shared fixtures: a demo Jellyfin server, optionally behind mutual TLS
with certificates made by openssl for each test session."""
import os
import subprocess
from pathlib import Path

import pytest

os.environ["EPHYRA_KEYRING"] = "memory"

from gi.repository import Gio, GLib  # noqa: E402

from ephyra.demo import DemoServer  # noqa: E402

DEMO = Path(__file__).resolve().parent / "data" / "demo"
P12_PASSWORD = "secret"


def run_until(predicate, timeout=10):
    """Iterate the default main context until predicate() is true."""
    context = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + timeout * 1_000_000
    while not predicate():
        if GLib.get_monotonic_time() > deadline:
            raise TimeoutError("main loop condition not reached")
        context.iteration(False)
        GLib.usleep(2000)


@pytest.fixture
def main_context():
    """The main thread owns the default main context for the whole test,
    as it does in the app's Gtk.Application.run(). While nobody owns it,
    g_main_context_invoke() from a GStreamer thread runs the callback on
    that thread, and gtk4paintablesink aborts ("Value accessed from
    different thread than where it was created"); holding it only inside
    run_until() left the test code between two calls unprotected. Only
    for tests that play media: a blocking TLS request on the main thread
    hangs while the thread owns the context, which the app never does
    (its requests run in tasks.py's threads)."""
    context = GLib.MainContext.default()
    context.acquire()
    yield context
    context.release()


@pytest.fixture(autouse=True)
def xdg(tmp_path, monkeypatch):
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    from ephyra import keyring
    keyring._memory.clear()


@pytest.fixture
def demo():
    server = DemoServer(DEMO).start()
    yield server
    server.stop()


def _openssl(*args, cwd):
    subprocess.run(["openssl", *args], cwd=cwd, check=True,
                   capture_output=True)


@pytest.fixture(scope="session")
def pki(tmp_path_factory):
    """CA, server certificate for 127.0.0.1, client certificate as PEM and
    as password-protected PKCS #12."""
    d = tmp_path_factory.mktemp("pki")
    _openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
             "-nodes", "-keyout", "ca.key", "-out", "ca.pem", "-days", "2",
             "-subj", "/CN=Ephyra Test CA", cwd=d)
    (d / "san.ext").write_text("subjectAltName=IP:127.0.0.1\n")
    (d / "client.ext").write_text("extendedKeyUsage=clientAuth\n")
    for name, subject, ext in (("server", "/CN=127.0.0.1", "san.ext"),
                               ("client", "/CN=Robin's phone", "client.ext")):
        _openssl("req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                 "-nodes", "-keyout", f"{name}.key", "-out", f"{name}.csr",
                 "-subj", subject, cwd=d)
        _openssl("x509", "-req", "-in", f"{name}.csr", "-CA", "ca.pem",
                 "-CAkey", "ca.key", "-CAcreateserial", "-days", "2",
                 "-extfile", ext, "-out", f"{name}.pem", cwd=d)
    (d / "client-combined.pem").write_bytes(
        (d / "client.pem").read_bytes() + (d / "client.key").read_bytes())
    _openssl("pkcs12", "-export", "-inkey", "client.key", "-in", "client.pem",
             "-out", "client.p12", "-passout", f"pass:{P12_PASSWORD}", cwd=d)
    return d


@pytest.fixture
def mtls_demo(pki):
    server = DemoServer(DEMO, tls=(pki / "server.pem", pki / "server.key",
                                   pki / "ca.pem")).start()
    yield server
    server.stop()


@pytest.fixture
def trust(pki):
    """A Gio.TlsDatabase that trusts the test CA."""
    return Gio.TlsFileDatabase.new(str(pki / "ca.pem"))
