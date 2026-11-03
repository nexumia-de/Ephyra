"""The server account on disk: addresses, home networks, user and device
ids, playback quality. Secrets (access token, certificate password) are in
the keyring (ephyra/keyring.py), the client certificate is a private copy
in the data directory. No GTK."""
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = 1
# Maximum streaming bitrate in bit/s; 0 plays the original file when the
# phone can decode it (docs/playback.md).
QUALITIES = (
    (0, "Original"),
    (20_000_000, "20 Mbit/s"),
    (8_000_000, "8 Mbit/s"),
    (4_000_000, "4 Mbit/s"),
    (1_500_000, "1.5 Mbit/s"),
)

# Light or dark (phosh-toolkit docs/design.md, rule 8): stored value,
# label, and the AdwColorScheme name it selects.
STYLES = (
    ("system", "Follow System", "DEFAULT"),
    ("light", "Light", "FORCE_LIGHT"),
    ("dark", "Dark", "FORCE_DARK"),
)


@dataclass
class Account:
    remote_url: str = ""
    local_url: str = ""
    home_networks: list = field(default_factory=list)
    certificate: bool = False
    server_id: str = ""
    server_name: str = ""
    user_id: str = ""
    user_name: str = ""
    device_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    quality_home: int = 0
    quality_away: int = 4_000_000
    style: str = "system"

    @property
    def signed_in(self):
        return bool(self.user_id and self.server_id)


def color_scheme(style):
    """The AdwColorScheme member name for a stored style."""
    for value, _, scheme in STYLES:
        if value == style:
            return scheme
    return "DEFAULT"


def _dir(env, default):
    base = os.environ.get(env) or str(Path.home() / default)
    return Path(base) / "ephyra"


def config_dir():
    return _dir("XDG_CONFIG_HOME", ".config")


def data_dir():
    return _dir("XDG_DATA_HOME", ".local/share")


def cache_dir():
    return _dir("XDG_CACHE_HOME", ".cache")


def certificate_path():
    """The private copy of the client certificate (PKCS #12 or PEM)."""
    return data_dir() / "client-certificate"


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "account.json"

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Account()
        except (OSError, ValueError):
            # Keep the broken file for a bug report and start over.
            self.path.replace(self.path.with_suffix(".bad"))
            return Account()
        known = Account.__dataclass_fields__
        return Account(**{k: v for k, v in data.get("account", {}).items()
                          if k in known})

    def save(self, account):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": VERSION,
                                   "account": asdict(account)}, indent=1),
                       encoding="utf-8")
        tmp.replace(self.path)


def save_certificate(data):
    """Keep a private copy of the certificate file the user picked, so the
    app does not depend on the original staying where it was."""
    path = certificate_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    tmp.replace(path)


def delete_certificate():
    certificate_path().unlink(missing_ok=True)
