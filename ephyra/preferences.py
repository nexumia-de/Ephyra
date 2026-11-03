"""Preferences: connection (the setup form), playback quality per route,
and the account."""
from gi.repository import Adw, GLib, Gtk

from ephyra import settings
from ephyra.setup import ConnectionForm


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, window):
        super().__init__(title="Preferences")
        self.window = window
        conn = window.connection
        account = conn.account

        connection_page = Adw.PreferencesPage(
            title="Connection", icon_name="network-server-symbolic")
        self.form = ConnectionForm(window, account, toast=self.toast)
        for group in self.form.groups:
            connection_page.add(group)
        actions = Adw.PreferencesGroup()
        self.save = Gtk.Button(label="Save and Reconnect",
                               halign=Gtk.Align.CENTER)
        self.save.add_css_class("pill")
        self.save.add_css_class("suggested-action")
        self.save.connect("clicked", self._on_save)
        actions.add(self.save)
        connection_page.add(actions)
        self.add(connection_page)

        playback_page = Adw.PreferencesPage(
            title="Playback", icon_name="media-playback-start-symbolic")
        quality = Adw.PreferencesGroup(
            title="Streaming Quality",
            description="Above this bitrate the server converts videos. "
                        "Original plays the file as it is when the phone "
                        "can decode it.")
        names = Gtk.StringList.new([name for _, name in settings.QUALITIES])
        for attr, title in (("quality_home", "At Home"),
                            ("quality_away", "Away")):
            row = Adw.ComboRow(title=title, model=names)
            values = [value for value, _ in settings.QUALITIES]
            current = getattr(account, attr)
            row.set_selected(values.index(current) if current in values else 0)
            row.connect("notify::selected", self._on_quality, attr, values)
            quality.add(row)
        playback_page.add(quality)
        self.add(playback_page)

        account_group = Adw.PreferencesGroup(title="Account")
        user = Adw.ActionRow(
            title=GLib.markup_escape_text(account.user_name or "Not signed in"),
            subtitle=GLib.markup_escape_text(account.server_name or ""))
        user.add_prefix(Gtk.Image(icon_name="avatar-default-symbolic"))
        sign_out = Gtk.Button(label="Sign Out", valign=Gtk.Align.CENTER)
        sign_out.add_css_class("destructive-action")
        sign_out.connect("clicked", self._on_sign_out)
        user.add_suffix(sign_out)
        account_group.add(user)
        connection_page.add(account_group)

    def toast(self, message):
        self.add_toast(Adw.Toast(title=GLib.markup_escape_text(message)))

    def _on_quality(self, row, pspec, attr, values):
        setattr(self.window.connection.account, attr, values[row.get_selected()])
        self.window.connection.save()

    def _on_save(self, *_):
        conn = self.window.connection

        def done(answers, http):
            self.save.set_sensitive(True)
            if answers is None:
                return
            ids = {a["Id"] for a in answers.values() if isinstance(a, dict)}
            if conn.account.server_id and conn.account.server_id not in ids:
                self.toast("That is a different server. Sign out first to "
                           "use it.")
                return
            self.form.apply(conn.account)
            conn.save()
            conn.load_certificate()
            conn.jellyfin.base_url = ""
            conn.resolve()
            self.toast("Saved")

        if self.form.check(done):
            self.save.set_sensitive(False)

    def _on_sign_out(self, *_):
        dialog = Adw.AlertDialog(
            heading="Sign Out?",
            body="Ephyra forgets your access token. The server address and "
                 "certificate stay.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("sign-out", "Sign Out")
        dialog.set_response_appearance("sign-out",
                                       Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_sign_out_response)
        dialog.present(self)

    def _on_sign_out_response(self, dialog, response):
        if response != "sign-out":
            return
        self.window.connection.sign_out()
        self.close()
        self.window.show_setup()

