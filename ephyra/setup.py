"""Connect and sign in: the server address, the client certificate and
the home network (docs/connection.md). The connection form
(phosh_toolkit.connection_form) is also the "Connection" page of the
preferences."""
from gi.repository import Adw, GLib, Gtk
from phosh_toolkit.connection_form import ConnectionForm, describe_error

from ephyra import USER_AGENT, connection, settings


def connection_form(window, account, toast=None):
    return ConnectionForm(
        window, account, settings.certificates(), connection.probe_with,
        USER_AGENT,
        server_description="The address you use to reach Jellyfin from anywhere",
        home_description="On these Wi-Fi networks Home Cinema talks to the server "
                         "directly. Leave the local address empty to always "
                         "use the server address.",
        toast=toast)


def _busy_button(label):
    button = Gtk.Button(label=label, halign=Gtk.Align.CENTER, margin_top=12)
    button.add_css_class("pill")
    button.add_css_class("suggested-action")
    return button


class SetupPage(Adw.NavigationPage):
    """First page: where the server is."""

    def __init__(self, window):
        super().__init__(title="Connect to Jellyfin", tag="setup")
        self.window = window
        conn = window.connection
        self.form = connection_form(window, conn.account)
        page = Adw.PreferencesPage()
        intro = Adw.PreferencesGroup()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(Gtk.Image(icon_name=window.app_icon, pixel_size=96))
        title = Gtk.Label(label="Welcome to Home Cinema", wrap=True,
                          justify=Gtk.Justification.CENTER)
        title.add_css_class("title-1")
        box.append(title)
        description = Gtk.Label(label="Watch your Jellyfin library on this "
                                      "phone", wrap=True,
                                justify=Gtk.Justification.CENTER)
        box.append(description)
        intro.add(box)
        page.add(intro)
        for group in self.form.groups:
            page.add(group)
        actions = Adw.PreferencesGroup()
        self.button = _busy_button("Connect")
        self.button.connect("clicked", self._on_connect)
        actions.add(self.button)
        page.add(actions)
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(Adw.HeaderBar(show_title=False))
        self.set_child(view)
        self.form.remote.connect("entry-activated", self._on_connect)

    def _on_connect(self, *_):
        def done(answers, http):
            self.button.set_sensitive(True)
            if answers is None:
                return
            info = self.form.answer(answers)
            url = self.form.reachable_url(answers)
            self.window.connection.jellyfin.http.certificate = http.certificate
            self.window.connection.jellyfin.http.cookies = http.cookies
            self.window.nav.push(SignInPage(self.window, self.form, info, url))

        if self.form.check(done):
            self.button.set_sensitive(False)


class SignInPage(Adw.NavigationPage):
    def __init__(self, window, form, info, url):
        name = info.get("ServerName") or "Jellyfin"
        super().__init__(title="Sign In", tag="sign-in")
        self.window, self.form, self.info, self.url = window, form, info, url
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title=GLib.markup_escape_text(name),
            description=f"Jellyfin {info.get('Version', '')}".strip())
        self.user = Adw.EntryRow(title="User Name",
                                 text=window.connection.account.user_name)
        self.password = Adw.PasswordEntryRow(title="Password")
        group.add(self.user)
        group.add(self.password)
        page.add(group)
        actions = Adw.PreferencesGroup()
        self.button = _busy_button("Sign In")
        self.button.connect("clicked", self._on_sign_in)
        actions.add(self.button)
        page.add(actions)
        self.password.connect("entry-activated", self._on_sign_in)
        self.user.connect("entry-activated", lambda *_: self.password.grab_focus())
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)
        self.connect("shown", lambda *_: self.user.grab_focus())

    def _on_sign_in(self, *_):
        user = self.user.get_text().strip()
        if not user:
            self.user.add_css_class("error")
            return
        conn = self.window.connection
        self.button.set_sensitive(False)

        def done(result, error):
            self.button.set_sensitive(True)
            if error is not None:
                self.password.add_css_class("error")
                self.window.toast(describe_error(error))
                return
            self.form.apply(conn.account)
            conn.save()
            conn.load_certificate()
            conn.resolve()
            self.window.show_library()

        connection.sign_in(conn, self.url, user, self.password.get_text(), done)
