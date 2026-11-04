"""Connect and sign in: the server address, the client certificate and
the home network (docs/connection.md). The connection form is also the
"Connection" page of the preferences."""
import logging

from gi.repository import Adw, Gio, GLib, Gtk

from ephyra import connection, keyring, network, route, settings, tls
from ephyra.http import CERTIFICATE_REQUIRED, AUTH, Client, HttpError

log = logging.getLogger("ephyra.setup")


def describe_error(error):
    if isinstance(error, HttpError):
        if error.kind == CERTIFICATE_REQUIRED:
            return "The server asks for a client certificate. Choose yours above."
        if error.kind == AUTH:
            return "Wrong user name or password"
        return str(error)
    return str(error) or "Something went wrong"


class ConnectionForm:
    """Groups for the remote address, client certificate and home network,
    filled from and saved to an Account."""

    def __init__(self, window, account, toast=None):
        self.window = window
        # Errors appear where the form is: the window or the preferences.
        self.toast = toast or window.toast
        self.certificate_data = None     # newly chosen file
        self.has_certificate = account.certificate
        self.networks = list(account.home_networks)

        self.server = Adw.PreferencesGroup(
            title="Server",
            description="The address you use to reach Jellyfin from anywhere")
        self.remote = Adw.EntryRow(title="Server Address",
                                   text=account.remote_url,
                                   input_purpose=Gtk.InputPurpose.URL)
        self.server.add(self.remote)
        self.cert_row = Adw.ActionRow(title="Client Certificate")
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        choose.add_css_class("flat")
        choose.connect("clicked", self._on_choose)
        self.cert_remove = Gtk.Button(icon_name="user-trash-symbolic",
                                      valign=Gtk.Align.CENTER,
                                      tooltip_text="Remove Certificate")
        self.cert_remove.add_css_class("flat")
        self.cert_remove.update_property([Gtk.AccessibleProperty.LABEL],
                                         ["Remove Certificate"])
        self.cert_remove.connect("clicked", self._on_remove_certificate)
        self.cert_row.add_suffix(self.cert_remove)
        self.cert_row.add_suffix(choose)
        self.server.add(self.cert_row)
        self.password = Adw.PasswordEntryRow(title="Certificate Password")
        self.server.add(self.password)

        self.home = Adw.PreferencesGroup(
            title="Home Network",
            description="On these Wi-Fi networks Ephyra talks to the server "
                        "directly. Leave the local address empty to always "
                        "use the server address.")
        self.local = Adw.EntryRow(title="Local Address", text=account.local_url,
                                  input_purpose=Gtk.InputPurpose.URL)
        self.home.add(self.local)
        self.network_rows = []
        self.add_current = Adw.ActionRow(title="Add Current Wi-Fi",
                                         activatable=True)
        self.add_current.add_prefix(Gtk.Image(icon_name="list-add-symbolic"))
        self.add_current.connect("activated", self._on_add_current)
        self.home.add(self.add_current)
        self.add_named = Adw.EntryRow(title="Add Wi-Fi by Name",
                                      show_apply_button=True)
        self.add_named.connect("apply", self._on_add_named)
        self.home.add(self.add_named)
        self._refresh_certificate(account.certificate and _saved_subtitle())
        self._refresh_networks()
        self._current_ssids = network.current_ssids()
        self._refresh_current()

    @property
    def groups(self):
        return [self.server, self.home]

    # --- certificate ---------------------------------------------------

    def _refresh_certificate(self, subtitle=None):
        has = self.has_certificate or self.certificate_data is not None
        self.cert_row.set_subtitle(subtitle or ("Chosen" if has else
                                   "None, only needed if the server asks for one"))
        self.cert_remove.set_visible(has)
        needs_password = (self.certificate_data is not None
                          and not tls.is_pem(self.certificate_data))
        self.password.set_visible(needs_password)

    def _on_choose(self, *_):
        dialog = Gtk.FileDialog(title="Choose Client Certificate")
        certs = Gtk.FileFilter(name="Certificates (.p12, .pfx, .pem)")
        for pattern in ("*.p12", "*.pfx", "*.pem", "*.crt"):
            certs.add_pattern(pattern)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(certs)
        dialog.set_filters(filters)
        dialog.open(self.window, None, self._on_chosen)

    def _on_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        try:
            data = file.load_bytes(None)[0].get_data()
        except GLib.Error as e:
            self.toast(e.message)
            return
        self.certificate_data = data
        self.cert_row.remove_css_class("error")
        self._refresh_certificate(file.get_basename())
        if self.password.get_visible():
            self.password.grab_focus()

    def _on_remove_certificate(self, *_):
        self.certificate_data = None
        self.has_certificate = False
        self.password.set_text("")
        self._refresh_certificate()

    def certificate(self):
        """The chosen Gio.TlsCertificate, the saved one, or None. Raises
        tls.CertificateError."""
        if self.certificate_data is not None:
            return tls.load(self.certificate_data, self.password.get_text())
        if self.has_certificate:
            return tls.load(settings.certificate_path().read_bytes(),
                            keyring.lookup(keyring.CERTIFICATE_PASSWORD))
        return None

    # --- home networks ---------------------------------------------------

    def _refresh_networks(self):
        for row in self.network_rows:
            self.home.remove(row)
        self.network_rows = []
        for ssid in self.networks:
            row = Adw.ActionRow(title=GLib.markup_escape_text(ssid))
            row.add_prefix(Gtk.Image(icon_name="network-wireless-symbolic"))
            remove = Gtk.Button(icon_name="list-remove-symbolic",
                                valign=Gtk.Align.CENTER,
                                tooltip_text="Remove Network")
            remove.add_css_class("flat")
            remove.update_property([Gtk.AccessibleProperty.LABEL],
                                   [f"Remove {ssid}"])
            remove.connect("clicked", self._on_remove_network, ssid)
            row.add_suffix(remove)
            self.home.add(row)
            self.network_rows.append(row)
        # Keep the add rows last.
        for row in (self.add_current, self.add_named):
            self.home.remove(row)
            self.home.add(row)

    def _refresh_current(self):
        ssids = sorted((self._current_ssids or set()) - set(self.networks))
        self.add_current.set_sensitive(bool(ssids))
        self.add_current.set_subtitle(
            GLib.markup_escape_text(", ".join(ssids)) if ssids else
            "Not connected to a Wi-Fi network" if self._current_ssids is not None
            else "Wi-Fi name not available")

    def _add(self, ssid):
        ssid = ssid.strip()
        if ssid and ssid not in self.networks:
            self.networks.append(ssid)
            self._refresh_networks()
            self._refresh_current()

    def _on_add_current(self, *_):
        for ssid in sorted((self._current_ssids or set()) - set(self.networks)):
            self._add(ssid)

    def _on_add_named(self, row):
        self._add(row.get_text())
        row.set_text("")

    def _on_remove_network(self, button, ssid):
        self.networks.remove(ssid)
        self._refresh_networks()
        self._refresh_current()

    # --- values ------------------------------------------------------------

    def addresses(self):
        """(remote, local) normalized; raises route.AddressError with the
        offending row marked."""
        values = []
        for row in (self.remote, self.local):
            row.remove_css_class("error")
            text = row.get_text().strip()
            if not text:
                values.append("")
                continue
            try:
                url = route.normalize(text)
            except route.AddressError:
                row.add_css_class("error")
                raise
            # Show what is used, e.g. with the added "https://".
            if url != text:
                row.set_text(url)
            values.append(url)
        if not any(values):
            self.remote.add_css_class("error")
            raise route.AddressError("Enter the server address")
        return tuple(values)

    def apply(self, account):
        """Write the form into `account` and keep the certificate."""
        account.remote_url, account.local_url = self.addresses()
        account.home_networks = list(self.networks)
        if self.certificate_data is not None:
            settings.save_certificate(self.certificate_data)
            password = self.password.get_text()
            if password:
                keyring.store(keyring.CERTIFICATE_PASSWORD, password)
            else:
                keyring.clear(keyring.CERTIFICATE_PASSWORD)
            account.certificate = True
        elif not self.has_certificate:
            settings.delete_certificate()
            keyring.clear(keyring.CERTIFICATE_PASSWORD)
            account.certificate = False

    def check(self, done):
        """Validate, load the certificate and ask the server(s).
        done(answers, http) on success; errors are shown as toasts."""
        try:
            remote, local = self.addresses()
            certificate = self.certificate()
        except route.AddressError as e:
            self.toast(str(e))
            return False
        except tls.PasswordNeeded as e:
            self.password.add_css_class("error")
            self.password.set_visible(True)
            self.toast(str(e))
            return False
        except (tls.CertificateError, OSError) as e:
            self.cert_row.add_css_class("error")
            self.toast(str(e))
            return False
        self.password.remove_css_class("error")
        http = Client()
        http.certificate = certificate

        def probed(answers, error):
            if error is not None:
                if getattr(error, "kind", None) == CERTIFICATE_REQUIRED:
                    self.cert_row.add_css_class("error")
                self.toast(describe_error(error))
                done(None, None)
                return
            local_answer = answers.get(route.LOCAL)
            if isinstance(local_answer, HttpError) and route.REMOTE in answers:
                self.toast("The local address does not answer from "
                                  "here; it is tried again at home")
            done(answers, http)

        connection.probe(http, remote, local, probed)
        return True


def _saved_subtitle():
    try:
        cert = tls.load(settings.certificate_path().read_bytes(),
                        keyring.lookup(keyring.CERTIFICATE_PASSWORD))
    except (OSError, tls.CertificateError) as e:
        return f"Can't be used: {e}"
    subject, expires = tls.describe(cert)
    if expires is not None:
        return f"{subject}, valid until {expires.format('%x')}"
    return subject


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
        self.form = ConnectionForm(window, conn.account)
        page = Adw.PreferencesPage()
        intro = Adw.PreferencesGroup()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(Gtk.Image(icon_name=window.app_icon, pixel_size=96))
        title = Gtk.Label(label="Welcome to Ephyra", wrap=True,
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
            info = next(a for a in answers.values() if isinstance(a, dict))
            url = (self.form.addresses()[1] if isinstance(answers.get(route.LOCAL), dict)
                   else self.form.addresses()[0])
            self.window.connection.jellyfin.http.certificate = http.certificate
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
