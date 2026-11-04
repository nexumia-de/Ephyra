import pytest

from ephyra import route
from ephyra.route import LOCAL, REMOTE, AddressError, candidates, normalize


@pytest.mark.parametrize("text, url", [
    # Without a scheme: https, also for local addresses.
    ("192.168.1.5:8096", "https://192.168.1.5:8096"),
    ("  media.example.org/ ", "https://media.example.org"),
    ("nas.local:8096", "https://nas.local:8096"),
    ("[fd00::5]:8096", "https://[fd00::5]:8096"),
    # A typed scheme is kept.
    ("http://192.168.1.5:8096", "http://192.168.1.5:8096"),
    ("https://media.example.org/jellyfin/", "https://media.example.org/jellyfin"),
    ("HTTP://10.0.0.2:8096", "http://10.0.0.2:8096"),
])
def test_normalize(text, url):
    assert normalize(text) == url


@pytest.mark.parametrize("text", ["", "ftp://x.org", "http://", "https://a.org:port"])
def test_normalize_rejects(text):
    with pytest.raises(AddressError):
        normalize(text)


LOCAL_URL = "http://192.168.1.5:8096"
REMOTE_URL = "https://media.example.org"


def test_home_network_prefers_local():
    assert candidates(REMOTE_URL, LOCAL_URL, ["Home"], {"Home"}) == [
        (LOCAL, LOCAL_URL), (REMOTE, REMOTE_URL)]


def test_other_network_never_tries_local():
    assert candidates(REMOTE_URL, LOCAL_URL, ["Home"], {"Café"}) == [
        (REMOTE, REMOTE_URL)]
    # Mobile data: connected to no Wi-Fi.
    assert candidates(REMOTE_URL, LOCAL_URL, ["Home"], set()) == [
        (REMOTE, REMOTE_URL)]


def test_without_list_or_networkmanager_local_first():
    assert candidates(REMOTE_URL, LOCAL_URL, [], {"Café"})[0] == (LOCAL, LOCAL_URL)
    assert candidates(REMOTE_URL, LOCAL_URL, ["Home"], None)[0] == (LOCAL, LOCAL_URL)


def test_single_address():
    assert candidates(REMOTE_URL, "", ["Home"], {"Home"}) == [(REMOTE, REMOTE_URL)]
    assert candidates("", LOCAL_URL, [], None) == [(LOCAL, LOCAL_URL)]


def test_local_timeout_is_short():
    assert route.TIMEOUT[LOCAL] < route.TIMEOUT[REMOTE]
