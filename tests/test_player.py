"""Player controls (docs/player-controls.md): which tap does what, and the
rotator that turns the player for a portrait phone held sideways."""
import os

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from conftest import run_until  # noqa: E402
from ephyra.player import tap_action, tap_zone  # noqa: E402

pytestmark = pytest.mark.usefixtures("main_context")


def test_tap_zones():
    assert tap_zone(10, 360) == "back"
    assert tap_zone(180, 360) == "center"
    assert tap_zone(350, 360) == "forward"
    assert tap_zone(10, 0) == "center"


def test_touch_double_tap_seeks_on_the_sides():
    # One tap might become a double tap: wait, then show or hide controls.
    assert tap_action(1, "back", touch=True) == "wait"
    assert tap_action(2, "back", touch=True) == "back"
    assert tap_action(2, "forward", touch=True) == "forward"
    # Every further quick tap seeks again.
    assert tap_action(4, "forward", touch=True) == "forward"
    # The middle answers at once; a double tap there does nothing more.
    assert tap_action(1, "center", touch=True) == "controls"
    assert tap_action(2, "center", touch=True) is None


def test_mouse_click_plays_double_click_fullscreens():
    assert tap_action(1, "back", touch=False) == "wait"
    assert tap_action(2, "back", touch=False) == "fullscreen"
    assert tap_action(2, "center", touch=False) == "fullscreen"
    assert tap_action(3, "center", touch=False) is None


@pytest.mark.skipif(not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
                    reason="needs a display")
def test_rotator_turns_child_and_input():
    from gi.repository import Graphene, Gtk

    from ephyra.rotator import Rotator

    child = Gtk.Box(hexpand=True, vexpand=True)
    rotator = Rotator(child)
    window = Gtk.Window(default_width=360, default_height=720, child=rotator)
    window.present()
    run_until(lambda: rotator.get_width() > 0)
    width, height = rotator.get_width(), rotator.get_height()
    assert rotator.props.portrait == (height > width)
    assert (child.get_width(), child.get_height()) == (width, height)

    rotator.props.rotated = True
    run_until(lambda: child.get_width() == height)
    assert child.get_height() == width
    # The child's top left corner is the screen's top right corner, so
    # the picture is upright when the phone is turned counter-clockwise.
    point = Graphene.Point()
    point.init(0, 0)
    ok, screen = child.compute_point(rotator, point)
    assert ok and (round(screen.x), round(screen.y)) == (width, 0)
    # Taps are turned as well: the screen's top right is the child's
    # top left area.
    assert rotator.pick(width - 5, 5, Gtk.PickFlags.DEFAULT) is child

    rotator.props.rotated = False
    run_until(lambda: child.get_width() == width)
    window.destroy()
