"""The whole flow through the real widgets against the demo server behind
mutual TLS: setup, sign in, home, a library, details, the player and the
preferences. Needs a display (CI runs pytest under xvfb-run)."""
import os
from pathlib import Path

import pytest

from conftest import P12_PASSWORD, owning_main_context, run_until

if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    pytest.skip("needs a display", allow_module_level=True)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from ephyra import connection, settings, setup  # noqa: E402
from ephyra.demo import PASSWORD  # noqa: E402
from ephyra.http import Client  # noqa: E402

CLIP = Path(__file__).resolve().parent / "data" / "media" / "clip.webm"
TRACKS = CLIP.with_name("tracks.mkv")


@pytest.fixture(scope="module")
def app():
    """One application for all tests: a second one with the same id can't
    register on the session bus."""
    from ephyra.main import Application
    application = Application()
    application.register(None)
    Adw.init()
    yield application


def visible(window):
    return window.nav.get_visible_page()


def test_setup_sign_in_browse_and_play(app, mtls_demo, pki, trust, monkeypatch):
    from ephyra.browse import MainPage
    from ephyra.detail import DetailPage
    from ephyra.player import PlayerPage
    from ephyra.preferences import PreferencesDialog
    from ephyra.window import Window

    def trusting_client():
        client = Client()
        client.tls_database = trust
        return client
    monkeypatch.setattr(setup, "Client", trusting_client)
    monkeypatch.setattr(connection.network, "current_ssids", lambda: {"Home"})

    conn = connection.Connection(watch=False)
    conn.jellyfin.http.tls_database = trust
    window = Window(app, conn)
    window.present()
    page = visible(window)
    assert isinstance(page, setup.SetupPage)

    # Without the certificate the server refuses, and the row is marked.
    page.form.remote.set_text(mtls_demo.url)
    page.form.local.set_text("http://127.0.0.1:9")
    page.form._add("Home")
    toasts = []
    monkeypatch.setattr(window, "toast", toasts.append)
    page.form.toast = window.toast
    page.button.emit("clicked")
    run_until(lambda: page.button.get_sensitive())
    assert "client certificate" in toasts[-1]
    assert page.form.cert_row.has_css_class("error")

    page.form.certificate_data = (pki / "client.p12").read_bytes()
    page.form.password.set_text(P12_PASSWORD)
    page.button.emit("clicked")
    run_until(lambda: isinstance(visible(window), setup.SignInPage))

    sign_in = visible(window)
    sign_in.user.set_text("robin")
    sign_in.password.set_text(PASSWORD)
    sign_in.button.emit("clicked")
    run_until(lambda: isinstance(visible(window), MainPage))

    account = settings.Store().load()
    assert account.signed_in and account.certificate
    assert account.home_networks == ["Home"]
    assert account.local_url == "http://127.0.0.1:9"
    assert settings.certificate_path().stat().st_mode & 0o777 == 0o600

    main = visible(window)
    run_until(lambda: main.views and "home" in main.content_pages
              and main.content_pages["home"].get_visible_child_name() == "content")
    # At "home" the local address is down, so the remote one is used.
    run_until(lambda: conn.state == "remote")

    window.show_view(1)
    movies = main.content_pages[main.views[0]["Id"]]
    run_until(lambda: movies.store.get_n_items() == 8)

    movie = movies.store.get_item(0).data
    window.show_item(movie)
    detail = visible(window)
    assert isinstance(detail, DetailPage)
    run_until(lambda: detail.stack.get_visible_child_name() == "content")

    with owning_main_context():
        # The demo "video" is not media: the player shows its error page and
        # offers server-side conversion.
        window.play(detail.item, 0)
        player = visible(window)
        assert isinstance(player, PlayerPage)
        run_until(lambda: player.stream is not None)
        assert player.stream.path.startswith(f"/Videos/{movie['Id']}/stream")
        run_until(lambda: player.stack.get_visible_child_name() == "error", 20)
        window.nav.pop()
        run_until(lambda: player.stopped)
        assert isinstance(visible(window), DetailPage)

        # A real clip: double tap seeks and shows the bubble, the rotate
        # button turns the player and goes fullscreen (docs/player-controls.md).
        mtls_demo.media = CLIP.read_bytes()
        window.play(detail.item, 2)
        player = visible(window)
        run_until(lambda: player.media is not None and player.media.is_seekable()
                  and player.position() >= 1.5, 20)
        player.media.pause()
        player.tap(1, "back", True)
        player.tap(2, "back", True)
        assert player.bubbles["back"].get_reveal_child()
        assert player.bubbles["back"].label.get_label() == "10 s"
        run_until(lambda: player.position() < 1)
        player.tap(3, "back", True)
        assert player.bubbles["back"].label.get_label() == "20 s"
        assert not player.center.get_reveal_child()
        player.toggle_rotation()
        assert player.rotator.props.rotated
        run_until(lambda: window.is_fullscreen())
        player.toggle_rotation()
        assert not player.rotator.props.rotated
        run_until(lambda: not window.is_fullscreen())
        window.nav.pop()
        run_until(lambda: player.stopped)

        # Audio and subtitles (docs/playback.md): German audio switches inside
        # GStreamer, the subtitle comes as SRT and Ephyra draws it.
        mtls_demo.media = TRACKS.read_bytes()
        mtls_demo.media_streams = [
            {"Index": 0, "Type": "Video", "Codec": "vp8"},
            {"Index": 1, "Type": "Audio", "Language": "eng", "DisplayTitle": "English"},
            {"Index": 2, "Type": "Audio", "Language": "ger", "DisplayTitle": "German"},
            {"Index": 3, "Type": "Subtitle", "Language": "eng", "DisplayTitle": "English"}]
        mtls_demo.subtitles = b"1\n00:00:00,000 --> 00:00:30,000\n<i>Hello</i>\n\n"
        window.play(detail.item, 0)
        player = visible(window)
        run_until(lambda: player.media is not None and player.media.is_prepared(), 20)
        assert player.tracks_button.get_visible()
        assert player.stream.audio_index == 1 and player.stream.subtitle_index == -1
        player.open_tracks()
        assert player.sheet.get_reveal_child()
        player.choose_audio(2)
        assert player.media.audio_position == 1
        media = player.media
        player.choose_subtitle(3)
        # No restart: the same pipeline plays on.
        assert player.media is media
        run_until(lambda: player.subtitle_label.get_visible(), 20)
        assert player.subtitle_label.get_label() == "<i>Hello</i>"
        assert any(path.endswith("/Subtitles/3/0/Stream.srt")
                   for _, path, _ in mtls_demo.requests)
        assert player.stream.report(0)["SubtitleStreamIndex"] == 3
        player.choose_subtitle(-1)
        run_until(lambda: not player.subtitle_label.get_visible())
        # A tap beside the sheet closes it.
        player._on_tap(None, 1, 1, 1)
        assert not player.sheet.get_reveal_child()
        window.nav.pop()
        run_until(lambda: player.stopped)
        mtls_demo.media_streams = []

    dialog = PreferencesDialog(window)
    dialog.present(window)
    assert dialog.form.remote.get_text() == mtls_demo.url
    # Style: follows the system until chosen, kept in the account file.
    manager = Adw.StyleManager.get_default()
    assert manager.get_color_scheme() == Adw.ColorScheme.DEFAULT
    dialog.style_row.set_selected(2)
    assert manager.get_color_scheme() == Adw.ColorScheme.FORCE_DARK
    assert settings.Store().load().style == "dark"
    dialog.style_row.set_selected(0)
    assert manager.get_color_scheme() == Adw.ColorScheme.DEFAULT
    dialog.close()
    window.destroy()


def test_server_rejecting_the_token_shows_setup(app, demo, monkeypatch):
    from ephyra import keyring
    from ephyra.window import Window
    monkeypatch.setattr(connection.network, "current_ssids", lambda: None)
    store = settings.Store()
    account = store.load()
    account.remote_url = demo.url
    account.server_id = demo.library["server"]["Id"]
    account.user_id = demo.library["user"]["Id"]
    store.save(account)
    keyring.store(keyring.TOKEN, "revoked")
    conn = connection.Connection(store, watch=False)
    window = Window(app, conn)
    window.present()
    run_until(lambda: isinstance(visible(window), setup.SetupPage))
    assert not conn.signed_in
    window.destroy()


