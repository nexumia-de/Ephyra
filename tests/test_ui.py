"""The whole flow through the real widgets against the demo server behind
mutual TLS: setup, sign in, home, a library, details, the player and the
preferences. Needs a display (CI runs pytest under xvfb-run)."""
import os

import pytest

from conftest import P12_PASSWORD, run_until

if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    pytest.skip("needs a display", allow_module_level=True)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from phosh_toolkit import connection_form, router  # noqa: E402
from phosh_toolkit.http import Client  # noqa: E402

from ephyra import connection, settings, setup  # noqa: E402
from ephyra.demo import PASSWORD  # noqa: E402


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

    def trusting_client(user_agent):
        client = Client(user_agent)
        client.tls_database = trust
        return client
    monkeypatch.setattr(connection_form, "Client", trusting_client)
    monkeypatch.setattr(router.network, "current_ssids", lambda: {"Home"})
    monkeypatch.setattr(connection_form.network, "current_ssids", lambda: {"Home"})

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
    monkeypatch.setattr(router.network, "current_ssids", lambda: None)
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


