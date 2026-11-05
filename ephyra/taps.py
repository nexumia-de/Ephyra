"""Taps on the video as phone players have them: which tap does what,
and the bubble that shows the seconds a double tap skipped
(docs/player-controls.md)."""
from gi.repository import GLib, Gtk

FEEDBACK_MS = 800      # how long the double-tap seek bubble stays


def tap_zone(x, width):
    """Left third, middle or right third of the video."""
    if width > 0 and x < width / 3:
        return "back"
    if width > 0 and x > width * 2 / 3:
        return "forward"
    return "center"


def tap_action(n, zone, touch):
    """What the `n`-th quick tap in `zone` does, as phone players do it:
    on touch, double tap on the sides seeks and every further quick tap
    seeks again; one tap shows or hides the controls. With a mouse, a
    click plays or pauses and a double click toggles fullscreen.
    "wait" means: act only if no second tap follows."""
    if touch:
        if zone == "center":
            return "controls" if n == 1 else None
        return "wait" if n == 1 else zone
    if n == 1:
        return "wait"
    return "fullscreen" if n == 2 else None


class SeekBubbles:
    """A round bubble on each side with an arrow and the seconds skipped
    so far; quick repeats on the same side add up."""

    def __init__(self):
        self.bubbles = {"back": _bubble("back"), "forward": _bubble("forward")}
        self._streak = (None, 0)    # side, seconds so far
        self._timeout = 0

    @property
    def overlays(self):
        return tuple(self.bubbles.values())

    def show(self, side, seconds):
        last, total = self._streak
        total = total + seconds if last == side else seconds
        self._streak = (side, total)
        bubble = self.bubbles[side]
        bubble.label.set_label(f"{total} s")
        bubble.set_reveal_child(True)
        self.bubbles["forward" if side == "back" else "back"].set_reveal_child(False)
        if self._timeout:
            GLib.source_remove(self._timeout)
        self._timeout = GLib.timeout_add(FEEDBACK_MS, self._end)

    def stop(self):
        if self._timeout:
            GLib.source_remove(self._timeout)
        self._end()

    def _end(self):
        self._timeout = 0
        self._streak = (None, 0)
        for bubble in self.bubbles.values():
            bubble.set_reveal_child(False)
        return GLib.SOURCE_REMOVE


def _bubble(side):
    icon = Gtk.Image(icon_name="media-seek-backward-symbolic" if side == "back"
                     else "media-seek-forward-symbolic")
    label = Gtk.Label(label="")
    label.add_css_class("numeric")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.add_css_class("osd")
    box.add_css_class("ephyra-seek-bubble")
    box.append(icon)
    box.append(label)
    revealer = Gtk.Revealer(child=box, can_target=False,
                            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                            halign=Gtk.Align.START if side == "back" else Gtk.Align.END,
                            valign=Gtk.Align.CENTER,
                            margin_start=24, margin_end=24)
    revealer.label = label
    return revealer
