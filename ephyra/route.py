"""Which server address to use: the local one at home, the remote one
elsewhere (docs/connection.md). Pure functions, no GTK."""
from urllib.parse import urlsplit, urlunsplit

LOCAL = "local"
REMOTE = "remote"

# Seconds to wait for /System/Info/Public. The local server answers within
# milliseconds or not at all; the remote one may sit behind mobile data.
TIMEOUT = {LOCAL: 3, REMOTE: 15}


class AddressError(ValueError):
    pass


def normalize(text):
    """A server address as typed by the user, as a base URL without a
    trailing slash. Without a scheme it gets "https://" (the owner's rule,
    docs/connection.md), for local addresses too; a typed "http://" or
    "https://" is kept. Raises AddressError for anything that is not an
    http(s) URL."""
    text = (text or "").strip()
    if not text:
        raise AddressError("Enter an address")
    if "://" not in text:
        text = f"https://{text}"
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AddressError("Use an address like https://media.example.org")
    try:
        parts.port
    except ValueError:
        raise AddressError("The port is not a number") from None
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def candidates(remote_url, local_url, home_networks, ssids):
    """Ordered (kind, url) pairs to try.

    `ssids` is the set of Wi-Fi networks the phone is connected to, or None
    when NetworkManager can't be asked. The local address is only tried on
    a listed home network, so the access token is never sent to a strange
    LAN; without a list (or without NetworkManager) it is tried first
    everywhere, and the server id check in Connection guards it."""
    order = []
    if local_url:
        if not home_networks or ssids is None:
            order.append((LOCAL, local_url))
        elif set(ssids) & set(home_networks):
            order.append((LOCAL, local_url))
    if remote_url:
        order.append((REMOTE, remote_url))
    return order
