"""The playbin player (ephyra/media.py) through the demo server and the
media proxy: what failed on the phone with Gtk.MediaFile, whose GStreamer
backend reads http:// through GIO. Video goes to a fakesink where
gtk4paintablesink is not installed; the data path is the same."""
from pathlib import Path

import pytest

from conftest import run_until

gi = pytest.importorskip("gi")
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from ephyra.api import Jellyfin  # noqa: E402
from ephyra.demo import PASSWORD  # noqa: E402
from ephyra.media import Media, init  # noqa: E402
from ephyra.proxy import MediaProxy  # noqa: E402

CLIP = Path(__file__).resolve().parent / "data" / "media" / "clip.webm"

init()
needed = ("playbin3", "matroskademux", "vp8dec", "vorbisdec", "souphttpsrc")
missing = [e for e in needed if Gst.ElementFactory.find(e) is None]
pytestmark = [pytest.mark.skipif(bool(missing), reason=f"GStreamer lacks {missing}"),
              pytest.mark.usefixtures("main_context")]


@pytest.fixture
def stream(demo):
    demo.media = CLIP.read_bytes()
    jellyfin = Jellyfin(device_id="test")
    jellyfin.base_url = demo.url
    jellyfin.authenticate("robin", PASSWORD)
    proxy = MediaProxy(jellyfin)
    yield proxy.url("/Videos/abc/stream?static=true")
    proxy.stop()


def make(url):
    media = Media(url)
    # No sound card in CI: a clocked fakesink keeps real-time playback.
    sink = Gst.ElementFactory.make("fakesink", None)
    sink.props.sync = True
    media.pipeline.props.audio_sink = sink
    return media


def test_plays_pauses_and_seeks_through_the_proxy(stream):
    media = make(stream)
    media.play()
    run_until(lambda: media.get_timestamp() > 500_000 or media.get_error(), 15)
    assert not media.get_error()
    assert media.is_prepared() and media.get_playing()
    assert 2_900_000 < media.get_duration() < 4_500_000
    media.pause()
    run_until(lambda: not media.get_playing(), 5)
    media.seek(2_000_000)
    media.play()
    run_until(lambda: media.get_ended() or media.get_error(), 15)
    assert media.get_ended() and not media.get_error()
    assert not media.get_playing()
    media.stop()


def test_undecodable_data_is_an_error(demo):
    # The demo server's default "media" is not a media file.
    jellyfin = Jellyfin(device_id="test")
    jellyfin.base_url = demo.url
    jellyfin.authenticate("robin", PASSWORD)
    proxy = MediaProxy(jellyfin)
    try:
        media = make(proxy.url("/Videos/abc/stream?static=true"))
        media.play()
        run_until(lambda: media.get_error(), 15)
        assert media.get_error() and not media.get_playing()
        media.stop()
    finally:
        proxy.stop()


def test_stop_releases_the_sink_on_the_main_thread(stream):
    # gtk4paintablesink aborts the process when it is freed on another
    # thread; Python's garbage collector may run on a proxy thread, so
    # stop() must leave nothing of it behind.
    import threading
    media = make(stream)
    media.play()
    run_until(lambda: media.is_prepared() or media.get_error(), 15)
    media.stop()
    assert media.pipeline is None and media.paintable is None
    media.seek(0)
    media.set_playing(True)
    holder = [media]
    del media
    thread = threading.Thread(target=holder.clear)
    thread.start()
    thread.join()


def test_chosen_audio_and_no_embedded_subtitle():
    # tracks.mkv: English and German audio and an embedded subtitle,
    # which playbin3 would show by itself; Ephyra draws subtitles itself.
    tracks = Path(__file__).resolve().parent / "data" / "media" / "tracks.mkv"
    media = Media(tracks.as_uri(), video=False, audio_position=1)
    media.pipeline.props.audio_sink = Gst.ElementFactory.make("fakesink", None)
    selected = []

    def on_message(bus, message):
        if message.type == Gst.MessageType.STREAMS_SELECTED:
            selected[:] = [message.streams_selected_get_stream(i)
                           for i in range(message.streams_selected_get_size())]

    def chosen():
        audio = [s.get_tags().get_string("language-code")[1] for s in selected
                 if s.get_stream_type() & Gst.StreamType.AUDIO]
        texts = [s for s in selected if s.get_stream_type() & Gst.StreamType.TEXT]
        return audio, len(texts)

    media.pipeline.get_bus().connect("message", on_message)
    try:
        media.play()
        # playbin3 first announces its own choice (English, the embedded
        # subtitle), then Ephyra's.
        run_until(lambda: chosen() == (["de"], 0) or media.get_error(), 15)
        assert not media.get_error()
        # Switching the audio track needs no restart.
        media.select_audio(0)
        run_until(lambda: chosen() == (["en"], 0) or media.get_error(), 15)
        assert not media.get_error()
        assert media.position_now() > 0
    finally:
        media.stop()
