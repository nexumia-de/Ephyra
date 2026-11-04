"""Shared fixtures: a demo Jellyfin server, optionally behind mutual TLS
with certificates made by openssl for each test session
(phosh_toolkit.testing)."""
import contextlib
import os
import sys
from pathlib import Path

import pytest

# The shared package from the sibling checkout (CI checks it out at the
# commit the Flatpak manifest pins).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "phosh-toolkit" / "lib"))
os.environ["EPHYRA_KEYRING"] = "memory"

from gi.repository import Gio, GLib  # noqa: E402
from phosh_toolkit.testing import P12_PASSWORD, make_pki, run_until  # noqa: E402,F401

from ephyra.demo import DemoServer  # noqa: E402

DEMO = Path(__file__).resolve().parent / "data" / "demo"


@contextlib.contextmanager
def owning_main_context():
    """The main thread owns the default main context, as it does in the
    app's Gtk.Application.run(). While nobody owns it,
    g_main_context_invoke() from a GStreamer thread runs the callback on
    that thread, and gtk4paintablesink aborts ("Value accessed from
    different thread than where it was created"); holding it only inside
    run_until() left the test code between two calls unprotected. Only
    around media playback (2026-11-04)."""
    context = GLib.MainContext.default()
    context.acquire()
    try:
        yield context
    finally:
        context.release()


@pytest.fixture
def main_context():
    with owning_main_context() as context:
        yield context


@pytest.fixture(autouse=True)
def xdg(tmp_path, monkeypatch):
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    from ephyra import keyring
    keyring.KEYRING.forget_memory()


@pytest.fixture
def demo():
    server = DemoServer(DEMO).start()
    yield server
    server.stop()


@pytest.fixture(scope="session")
def pki(tmp_path_factory):
    """CA, server certificate for 127.0.0.1, client certificate as PEM and
    as password-protected PKCS #12."""
    return make_pki(tmp_path_factory.mktemp("pki"))


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
