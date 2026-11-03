"""Access token and certificate password in the keyring (libsecret; in the
Flatpak through the Secret portal). EPHYRA_KEYRING=memory keeps them in
memory only, for tests and screenshots."""
import logging
import os

log = logging.getLogger("ephyra.keyring")

TOKEN = "token"
CERTIFICATE_PASSWORD = "certificate-password"
_LABELS = {TOKEN: "Ephyra access token",
           CERTIFICATE_PASSWORD: "Ephyra client certificate password"}

_memory = {}
_schema = None


def _secret():
    global _schema
    if os.environ.get("EPHYRA_KEYRING") == "memory":
        return None
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
    except (ImportError, ValueError):
        log.warning("libsecret not available, secrets are kept in memory")
        return None
    if _schema is None:
        _schema = Secret.Schema.new(
            "de.nexumia.Ephyra", Secret.SchemaFlags.NONE,
            {"kind": Secret.SchemaAttributeType.STRING})
    return Secret


def store(kind, value):
    Secret = _secret()
    if Secret is None:
        _memory[kind] = value
        return
    try:
        Secret.password_store_sync(_schema, {"kind": kind},
                                   Secret.COLLECTION_DEFAULT, _LABELS[kind],
                                   value, None)
    except Exception as e:  # GLib.Error: no keyring daemon, locked, …
        log.warning("keyring: %s; keeping %s in memory", e, kind)
        _memory[kind] = value


def lookup(kind):
    if kind in _memory:
        return _memory[kind]
    Secret = _secret()
    if Secret is None:
        return None
    try:
        return Secret.password_lookup_sync(_schema, {"kind": kind}, None)
    except Exception as e:
        log.warning("keyring: %s", e)
        return None


def clear(kind):
    _memory.pop(kind, None)
    Secret = _secret()
    if Secret is None:
        return
    try:
        Secret.password_clear_sync(_schema, {"kind": kind}, None)
    except Exception as e:
        log.warning("keyring: %s", e)
