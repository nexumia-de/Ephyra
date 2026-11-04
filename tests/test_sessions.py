"""The server side of the player's streams (ephyra/sessions.py,
docs/playback.md) against the demo server: every stream that was chosen
is stopped on the server, a converted one also with DELETE
/Videos/ActiveEncodings, answers that come too late are stopped instead
of played, and a burned-in default subtitle is not used."""
import pytest

from ephyra import playback
from ephyra.api import Jellyfin
from ephyra.demo import TOKEN
from ephyra.sessions import Sessions, fetch_stream

PGS = [
    {"Index": 0, "Type": "Video", "Codec": "h264"},
    {"Index": 1, "Type": "Audio", "Codec": "truehd", "DisplayTitle": "English - TrueHD 7.1"},
    {"Index": 2, "Type": "Subtitle", "Codec": "PGSSUB", "IsTextSubtitleStream": False,
     "IsDefault": True, "DisplayTitle": "English - PGS"},
    {"Index": 3, "Type": "Subtitle", "Codec": "subrip", "IsTextSubtitleStream": True,
     "DisplayTitle": "German - SRT"},
]


class Calls:
    """Connection.call stand-in: runs the work at once, and delivers the
    answers when the test says so (the main loop in the app)."""

    def __init__(self):
        self.pending = []

    def __call__(self, fn, done, *args):
        try:
            result, error = fn(*args), None
        except Exception as e:  # noqa: BLE001
            result, error = None, e
        self.pending.append((done, result, error))

    def deliver(self):
        while self.pending:
            done, result, error = self.pending.pop(0)
            if done is not None:
                done(result, error)


@pytest.fixture
def jellyfin(demo):
    client = Jellyfin(device_id="phone")
    client.base_url = demo.url
    client.token = TOKEN
    client.user_id = demo.library["user"]["Id"]
    return client


@pytest.fixture
def movie(demo):
    return next(i for i in demo.library["items"] if i["Type"] == "Movie")


def stops(demo):
    return [(path, p["PlaySessionId"], p.get("Failed", False))
            for path, p in demo.reports if path.endswith("/Stopped")]


def test_converted_stream_is_stopped_and_its_encoding_deleted(demo, jellyfin, movie):
    demo.transcode = True
    calls = Calls()
    sessions = Sessions(jellyfin, calls)
    got = []
    sessions.open(lambda s, e: got.append(s), movie, 0)
    calls.deliver()
    stream = got[0]
    assert stream.method == playback.TRANSCODE
    # Left before GStreamer had it prepared: it never played.
    sessions.stop(stream, position=120, failed=True)
    calls.deliver()
    assert stops(demo) == [("/Sessions/Playing/Stopped", stream.play_session_id, True)]
    assert demo.reports[-1][1]["PositionTicks"] == 1_200_000_000
    assert demo.stopped_encodings == [("phone", stream.play_session_id)]


def test_direct_play_is_stopped_without_an_encoding_delete(demo, jellyfin, movie):
    calls = Calls()
    sessions = Sessions(jellyfin, calls)
    got = []
    sessions.open(lambda s, e: got.append(s), movie, 0)
    calls.deliver()
    assert got[0].method == playback.DIRECT_PLAY
    sessions.stop(got[0], position=30)
    calls.deliver()
    assert stops(demo) == [("/Sessions/Playing/Stopped", got[0].play_session_id, False)]
    assert demo.stopped_encodings == []


def test_replaced_stream_is_stopped_before_the_new_request(demo, jellyfin, movie):
    """Reload (other audio, burned subtitle) and Convert on the Server:
    the old session ends before PlaybackInfo is asked again."""
    demo.transcode = True
    calls = Calls()
    sessions = Sessions(jellyfin, calls)
    got = []
    sessions.open(lambda s, e: got.append(s), movie, 0)
    calls.deliver()
    old = got[0]
    demo.requests.clear()
    sessions.open(lambda s, e: got.append(s), movie, 0, force=True,
                  replace=(old, 0, True))
    calls.deliver()
    new = got[1]
    assert new.play_session_id != old.play_session_id
    order = [(m, path) for m, path, _ in demo.requests]
    assert order == [("POST", "/Sessions/Playing/Stopped"),
                     ("DELETE", "/Videos/ActiveEncodings"),
                     ("POST", f"/Items/{movie['Id']}/PlaybackInfo")]
    assert demo.stopped_encodings == [("phone", old.play_session_id)]


def test_late_answer_after_close_is_stopped_not_played(demo, jellyfin, movie):
    demo.transcode = True
    calls = Calls()
    sessions = Sessions(jellyfin, calls)
    got = []
    sessions.open(lambda s, e: got.append(s), movie, 0)
    sessions.close()            # the page closed while the server answered
    calls.deliver()
    assert got == []
    session = f"demo-session-{demo.sessions}"
    assert stops(demo) == [("/Sessions/Playing/Stopped", session, True)]
    assert demo.stopped_encodings == [("phone", session)]


def test_answer_to_an_older_request_is_stopped(demo, jellyfin, movie):
    demo.transcode = True
    calls = Calls()
    sessions = Sessions(jellyfin, calls)
    got = []
    sessions.open(lambda s, e: got.append(("first", s)), movie, 0)
    sessions.open(lambda s, e: got.append(("second", s)), movie, 0)
    calls.deliver()
    assert [name for name, _ in got] == ["second"]
    assert demo.stopped_encodings == [("phone", "demo-session-1")]


def test_burned_in_default_subtitle_is_turned_off(demo, jellyfin, movie):
    """A PGS default subtitle would make the server re-encode the whole
    video (owner's server, 2026-11-04): ask again with subtitle -1."""
    demo.media_streams = PGS
    stream = fetch_stream(jellyfin, movie, 0)
    assert [p.get("SubtitleStreamIndex") for p in demo.playback_requests] == [None, -1]
    assert stream.method == playback.DIRECT_PLAY
    assert stream.subtitle_index == -1
    # Still offered, and marked.
    assert playback.subtitle_tracks(stream.source) == [
        (2, "English - PGS (converted on the server)"), (3, "German - SRT")]


def test_chosen_picture_subtitle_is_burned_in(demo, jellyfin, movie):
    demo.media_streams = PGS
    stream = fetch_stream(jellyfin, movie, 0, subtitle=2)
    assert [p.get("SubtitleStreamIndex") for p in demo.playback_requests] == [2]
    assert stream.method == playback.TRANSCODE and stream.subtitle_index == 2


def test_text_default_subtitle_stays(demo, jellyfin, movie):
    demo.media_streams = [dict(s, IsDefault=s["Index"] == 3) for s in PGS]
    stream = fetch_stream(jellyfin, movie, 0)
    assert len(demo.playback_requests) == 1
    assert stream.subtitle_index == 3 and stream.subtitle_path.endswith("/3/0/Stream.srt")


def test_track_choice_names_its_media_source(demo, jellyfin, movie):
    """Jellyfin ignores AudioStreamIndex and SubtitleStreamIndex without
    the MediaSourceId (MediaInfoHelper.SetDeviceSpecificData): a chosen
    subtitle then jumped back to the server's default (owner, 2026-11-04)."""
    demo.media_streams = PGS
    stream = fetch_stream(jellyfin, movie, 0, subtitle=-1)
    assert demo.playback_requests[-1]["MediaSourceId"] == movie["Id"]
    assert stream.subtitle_index == -1 and stream.method == playback.DIRECT_PLAY
    stream = fetch_stream(jellyfin, movie, 0, audio=1, subtitle=3,
                          source=stream.media_source_id)
    assert stream.subtitle_index == 3 and stream.audio_index == 1
    # The first request leaves the choice, and the source, to the server.
    fetch_stream(jellyfin, movie, 0)
    assert demo.playback_requests[-2].get("MediaSourceId") is None
