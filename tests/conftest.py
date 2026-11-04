"""Shared fixtures: a demo Jellyfin server, optionally behind mutual TLS
with certificates made by openssl for each test session
(phosh_toolkit.testing)."""
import os
import sys
from pathlib import Path

import pytest

# The shared package from the sibling checkout (CI checks it out at the
# commit the Flatpak manifest pins).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "phosh-toolkit" / "lib"))
os.environ["EPHYRA_KEYRING"] = "memory"

from gi.repository import Gio  # noqa: E402
from phosh_toolkit.testing import P12_PASSWORD, make_pki, run_until  # noqa: E402,F401

from ephyra.demo import DemoServer  # noqa: E402

DEMO = Path(__file__).resolve().parent / "data" / "demo"


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
