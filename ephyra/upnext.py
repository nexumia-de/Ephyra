"""The up-next card in the player's bottom right corner: the next episode
with a countdown, Play Now and Cancel (docs/player-controls.md)."""
from gi.repository import GObject, Gtk, Pango

from ephyra import images, text, widgets

COUNTDOWN = 10   # seconds from showing the card to the next episode


class UpNextCard(Gtk.Revealer):
    """Emits `play` when the countdown ran out or Play Now was pressed,
    `cancel` when Cancel was pressed. The player counts the seconds down
    with count_down(), only while it plays."""

    __gsignals__ = {
        "play": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "cancel": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, images_):
        super().__init__(reveal_child=False, can_target=False,
                         transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                         halign=Gtk.Align.END, valign=Gtk.Align.END,
                         margin_start=12, margin_end=12)
        self.images = images_
        self.remaining = 0
        self.episode = None
        self.art = widgets.Artwork(16 / 9, natural_width=112)
        self.art.set_size_request(112, -1)
        self.art.set_valign(Gtk.Align.CENTER)
        self.art.placeholder.set_pixel_size(24)
        self.countdown = Gtk.Label(xalign=0)
        self.countdown.add_css_class("caption")
        self.countdown.add_css_class("numeric")
        self.title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END,
                               max_width_chars=24)
        self.title.add_css_class("heading")
        play = Gtk.Button(label="Play Now")
        play.add_css_class("pill")
        play.add_css_class("suggested-action")
        play.connect("clicked", lambda *_: self.emit("play"))
        cancel = Gtk.Button(label="Cancel")
        cancel.add_css_class("pill")
        cancel.connect("clicked", lambda *_: self.emit("cancel"))
        buttons = Gtk.Box(spacing=6)
        buttons.append(play)
        buttons.append(cancel)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       valign=Gtk.Align.CENTER)
        info.append(self.countdown)
        info.append(self.title)
        info.append(buttons)
        box = Gtk.Box(spacing=12)
        box.add_css_class("osd")
        box.add_css_class("ephyra-upnext")
        box.append(self.art)
        box.append(info)
        self.set_child(box)

    @property
    def shown(self):
        return self.get_reveal_child()

    def offer(self, episode):
        """Show `episode` and start the countdown."""
        if episode is not self.episode:
            self.episode = episode
            code = text.episode_code(episode)
            name = episode.get("Name", "")
            self.title.set_label(f"{code} · {name}" if code else name)
            self.art.show(self.images, images.landscape(episode), 224,
                          widgets.icon_for(episode))
        self.remaining = COUNTDOWN
        self._update_countdown()
        # Only while shown: hidden, the revealer would still take the taps
        # on the video beneath it (docs/player-controls.md).
        self.set_can_target(True)
        self.set_reveal_child(True)

    def count_down(self):
        """One second passed while playing; `play` when it reaches 0."""
        if not self.shown:
            return
        self.remaining -= 1
        self._update_countdown()
        if self.remaining <= 0:
            self.emit("play")

    def withdraw(self):
        self.set_can_target(False)
        self.set_reveal_child(False)

    def _update_countdown(self):
        seconds = max(0, self.remaining)
        self.countdown.set_label(f"Next episode in {seconds} s")
