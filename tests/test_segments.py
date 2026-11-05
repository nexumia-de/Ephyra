"""Skip buttons and the next episode (ephyra/segments.py, the API calls
against the demo server; docs/player-controls.md)."""
from datetime import datetime

import pytest

from ephyra import segments, text
from ephyra.api import Jellyfin, HttpError
from ephyra.demo import TOKEN

T = segments.TICKS
S1E6 = "770b908b6aad4ce9da249cbe6fd219cd"
S2E1 = "290cd9a50691e695710c310a60ab9853"
NIGHT_MARKET_LAST = "32191c731b6f1da02c23f5b436fbf934"


def test_parse_keeps_known_segments_in_order():
    answer = {"Items": [
        {"Type": "Outro", "StartTicks": 1300 * T, "EndTicks": 1400 * T},
        {"Type": "Intro", "StartTicks": 30 * T, "EndTicks": 90 * T},
        {"Type": "Unknown", "StartTicks": 0, "EndTicks": 10 * T},
        {"Type": "Recap", "StartTicks": 0, "EndTicks": int(0.5 * T)}]}
    assert segments.parse(answer) == [segments.Segment("Intro", 30, 90),
                                      segments.Segment("Outro", 1300, 1400)]
    assert segments.parse(None) == []


def test_segment_at_position():
    found = [segments.Segment("Intro", 30, 90)]
    assert segments.at(found, 29) is None
    assert segments.at(found, 30).kind == "Intro"
    assert segments.at(found, 88.9).kind == "Intro"
    # The last second is not worth a button.
    assert segments.at(found, 89.5) is None


def test_up_next_at_the_credits_or_30_seconds_before_the_end():
    credits = [segments.Segment("Intro", 30, 90), segments.Segment("Outro", 1300, 1400)]
    assert segments.up_next_from(credits, 1400) == 1300
    # An "outro" early in the episode (a cold open's end) is not the credits.
    early = [segments.Segment("Outro", 100, 200)]
    assert segments.up_next_from(early, 1400) == 1370
    assert segments.up_next_from([], 20) == 0
    assert segments.up_next_from([], 0) is None


def test_ends_after():
    assert text.ends_after(datetime(2026, 11, 5, 21, 50), 25 * 60) == "Ends at 22:15"
    assert text.ends_after(datetime(2026, 11, 5, 21, 50), -5) == "Ends at 21:50"


@pytest.fixture
def jellyfin(demo):
    client = Jellyfin(device_id="phone")
    client.base_url = demo.url
    client.token = TOKEN
    client.user_id = demo.library["user"]["Id"]
    return client


def test_next_episode_crosses_seasons_and_ends(demo, jellyfin):
    items = demo.items
    assert jellyfin.next_episode(items[S1E6])["Id"] == S2E1
    assert jellyfin.next_episode(items[NIGHT_MARKET_LAST]) is None
    movie = next(i for i in demo.library["items"] if i["Type"] == "Movie")
    assert jellyfin.next_episode(movie) is None


def test_media_segments_on_old_and_new_servers(demo, jellyfin, monkeypatch):
    demo.segments[S1E6] = [{"Type": "Intro", "StartTicks": 0, "EndTicks": 50 * T}]
    assert jellyfin.media_segments(S1E6)["Items"][0]["Type"] == "Intro"
    assert jellyfin.media_segments(S2E1) == {"Items": [], "TotalRecordCount": 0}
    # Jellyfin 10.9 has no MediaSegments: 404 counts as none.
    monkeypatch.setattr(jellyfin, "get", _raise(404))
    assert jellyfin.media_segments(S1E6) == {"Items": []}
    monkeypatch.setattr(jellyfin, "get", _raise(500))
    with pytest.raises(HttpError):
        jellyfin.media_segments(S1E6)


def _raise(status):
    def get(*args, **kwargs):
        raise HttpError("server", f"Server error {status}", status)
    return get
