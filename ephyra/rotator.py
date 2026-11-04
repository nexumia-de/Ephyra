"""A container that can show its child turned by a quarter, so a video
fills a portrait phone held sideways (docs/player-controls.md).

Phosh rotates the whole display only through the compositor's
org.gnome.Mutter.DisplayConfig API, which a Flatpak can't reach without an
extra permission and which fights the user's auto-rotate setting. Turning
the player inside the window needs neither. GTK applies the allocation
transform to drawing and to input, so taps land on the turned widgets.
"""
from gi.repository import GLib, GObject, Graphene, Gsk, Gtk


class Rotator(Gtk.Widget):
    __gtype_name__ = "EphyraRotator"

    def __init__(self, child):
        super().__init__()
        self._rotated = False
        self._portrait = None
        self.child = child
        child.set_parent(self)
        self.set_overflow(Gtk.Overflow.HIDDEN)

    @GObject.Property(type=bool, default=False)
    def rotated(self):
        """Child turned 90° clockwise: its top is the screen's right edge,
        as when the phone is turned counter-clockwise."""
        return self._rotated

    @rotated.setter
    def rotated(self, value):
        if value != self._rotated:
            self._rotated = value
            self.queue_resize()

    @GObject.Property(type=bool, default=True)
    def portrait(self):
        """The space the rotator got is taller than wide."""
        return self._portrait is not False

    def do_measure(self, orientation, for_size):
        if self._rotated:
            orientation = (Gtk.Orientation.VERTICAL
                           if orientation == Gtk.Orientation.HORIZONTAL
                           else Gtk.Orientation.HORIZONTAL)
            minimum, natural, _, _ = self.child.measure(orientation, for_size)
            return minimum, natural, -1, -1
        return self.child.measure(orientation, for_size)

    def do_size_allocate(self, width, height, baseline):
        if self._rotated:
            point = Graphene.Point()
            point.init(width, 0)
            transform = Gsk.Transform.new().translate(point).rotate(90)
            self.child.allocate(height, width, -1, transform)
        else:
            self.child.allocate(width, height, baseline, None)
        portrait = height > width
        if portrait != self._portrait:
            self._portrait = portrait
            # Not during allocation: listeners may change widgets.
            GLib.idle_add(self.notify, "portrait")

    def do_dispose(self):
        if self.child is not None:
            self.child.unparent()
            self.child = None
