"""Shared widgets: poster cards, card grids, loading and error pages."""
from gi.repository import Adw, GObject, Gtk, Pango

from ephyra import images, text

POSTER_WIDTH = 150      # two columns at 360 px
LANDSCAPE_WIDTH = 150   # two per row at 360 px: 2 × (150 + 6 padding) + 12 + 24


class Item(GObject.Object):
    """A Jellyfin item (its JSON dict) in a Gio.ListStore."""

    def __init__(self, data):
        super().__init__()
        self.data = data


def spinner():
    if hasattr(Adw, "Spinner"):    # libadwaita 1.6
        return Adw.Spinner(width_request=32, height_request=32)
    widget = Gtk.Spinner(width_request=32, height_request=32)
    widget.start()
    return widget


def loading_page():
    page = Adw.StatusPage(vexpand=True)
    page.set_child(spinner())
    return page


def error_page(title, description, retry=None):
    page = Adw.StatusPage(icon_name="network-error-symbolic", title=title,
                          description=description, vexpand=True)
    if retry:
        button = Gtk.Button(label="Retry", halign=Gtk.Align.CENTER)
        button.add_css_class("pill")
        button.connect("clicked", lambda *_: retry())
        page.set_child(button)
    return page


def icon_for(item):
    kind = item.get("Type")
    if kind in ("MusicAlbum", "Audio") or item.get("CollectionType") == "music":
        return "folder-music-symbolic"
    if kind in ("Series", "Season", "Episode") or item.get("CollectionType") == "tvshows":
        return "video-display-symbolic"
    if kind == "CollectionFolder" or kind == "Folder" or kind == "BoxSet":
        return "folder-videos-symbolic"
    return "video-x-generic-symbolic"


class Ratio(Gtk.Widget):
    """Gives its child the height that matches its width at a fixed aspect
    ratio (width / height), also before an image is loaded."""

    def __init__(self, ratio, child, natural_width=0, max_height=0):
        super().__init__()
        self.ratio = ratio
        # Wide windows: crop instead of growing past this (0: no limit).
        self.max_height = max_height
        self.natural_width = natural_width
        self.child = child
        child.set_parent(self)

    def set_ratio(self, ratio):
        if ratio != self.ratio:
            self.ratio = ratio
            self.queue_resize()

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            minimum = self.child.measure(orientation, -1)[0]
            return minimum, max(minimum, self.natural_width), -1, -1
        width = for_size if for_size > 0 else self.natural_width
        height = int(round(width / self.ratio))
        if self.max_height:
            height = min(height, self.max_height)
        return height, height, -1, -1

    def do_size_allocate(self, width, height, baseline):
        self.child.allocate(width, height, baseline, None)

    def do_dispose(self):
        if self.child is not None:
            self.child.unparent()
            self.child = None


class Artwork(Gtk.Overlay):
    """An image of fixed aspect ratio, rounded, with a placeholder icon
    until it loads."""

    def __init__(self, ratio, css="ephyra-poster", natural_width=0,
                 max_height=0):
        super().__init__()
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER,
                                   can_shrink=True)
        self.placeholder = Gtk.Image(pixel_size=48, opacity=0.4)
        box = Gtk.Overlay(overflow=Gtk.Overflow.HIDDEN)
        box.add_css_class(css)
        box.set_child(self.picture)
        box.add_overlay(self.placeholder)
        self.frame = Ratio(ratio, box, natural_width, max_height)
        self.set_child(self.frame)
        self._key = None

    def show(self, images_, ref, width, icon):
        """ref: (item id, kind, tag) or None."""
        self.placeholder.set_from_icon_name(icon)
        self.placeholder.set_visible(True)
        self.picture.set_paintable(None)
        self._key = ref
        if ref is None or not ref[0]:
            return
        def done(texture, key=ref):
            if texture is not None and key == self._key:
                self.picture.set_paintable(texture)
                self.placeholder.set_visible(False)
        images_.load(ref[0], ref[1], ref[2], width, done)


class Card(Gtk.Box):
    """Poster (2:3), square (albums) or landscape (16:9) card with title,
    subtitle, played badge and resume progress, as on Jellyfin's home."""

    def __init__(self, images_, shape="poster"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.images = images_
        self.shape = shape
        width = LANDSCAPE_WIDTH if shape == "landscape" else POSTER_WIDTH
        self.set_size_request(width, -1)
        ratio = 16 / 9 if shape == "landscape" else 2 / 3
        self.art = Artwork(ratio, natural_width=width)
        self.badge = Gtk.Label(halign=Gtk.Align.END, valign=Gtk.Align.START)
        self.badge.add_css_class("ephyra-badge")
        self.badge.add_css_class("caption-heading")
        self.check = Gtk.Image(icon_name="object-select-symbolic",
                               halign=Gtk.Align.END, valign=Gtk.Align.START)
        self.check.add_css_class("ephyra-badge")
        self.progress = Gtk.ProgressBar(valign=Gtk.Align.END)
        self.progress.add_css_class("osd")
        self.progress.add_css_class("ephyra-poster-progress")
        for widget in (self.badge, self.check, self.progress):
            self.art.add_overlay(widget)
        self.append(self.art)
        self.title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END,
                               max_width_chars=1, hexpand=True)
        self.title.add_css_class("heading")
        self.subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                  max_width_chars=1)
        self.subtitle.add_css_class("caption")
        self.subtitle.add_css_class("dimmed")
        self.subtitle.add_css_class("dim-label")   # libadwaita < 1.7
        self.append(self.title)
        self.append(self.subtitle)

    def set_item(self, item):
        self.item = item
        square = item.get("Type") in ("MusicAlbum", "Audio")
        self.art.frame.set_ratio(16 / 9 if self.shape == "landscape"
                                 else 1 if square else 2 / 3)
        if self.shape == "landscape":
            ref = images.landscape(item)
            width = LANDSCAPE_WIDTH
        else:
            ref = images.primary(item)
            width = POSTER_WIDTH
        if item.get("Type") == "CollectionFolder":
            self.art.frame.set_ratio(16 / 9)
        self.art.show(self.images, ref, width, icon_for(item))
        self.title.set_label(text.title(item))
        self.subtitle.set_label(text.subtitle(item))
        self.subtitle.set_visible(bool(self.subtitle.get_label()))
        data = item.get("UserData") or {}
        unplayed = data.get("UnplayedItemCount") or 0
        self.badge.set_label(str(unplayed))
        self.badge.set_visible(item.get("Type") == "Series" and unplayed > 0)
        self.check.set_visible(bool(data.get("Played")) and not self.badge.get_visible())
        fraction = text.played_fraction(item)
        self.progress.set_fraction(fraction)
        self.progress.set_visible(0 < fraction < 1 and not data.get("Played"))
        self.update_property([Gtk.AccessibleProperty.LABEL],
                             [f"{text.title(item)} {self.subtitle.get_label()}".strip()])


def card_box(images_, items, on_activate, shape="poster"):
    """A FlowBox of cards for short lists (home sections)."""
    flow = Gtk.FlowBox(homogeneous=True,
                       max_children_per_line=12, row_spacing=18,
                       column_spacing=12,
                       selection_mode=Gtk.SelectionMode.NONE,
                       activate_on_single_click=True, valign=Gtk.Align.START)
    flow.set_min_children_per_line(2)
    for item in items:
        card = Card(images_, shape)
        card.set_item(item)
        flow.append(card)
    flow.connect("child-activated",
                 lambda f, child: on_activate(child.get_child().item))
    return flow


class CardGrid(Gtk.GridView):
    """A recycling grid of poster cards for whole libraries."""

    def __init__(self, images_, store, on_activate):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", lambda f, li: li.set_child(Card(images_)))
        factory.connect("bind", lambda f, li: li.get_child().set_item(
            li.get_item().data))
        super().__init__(model=Gtk.NoSelection(model=store), factory=factory,
                         min_columns=2, max_columns=12,
                         single_click_activate=True)
        self.connect("activate", lambda grid, pos: on_activate(
            store.get_item(pos).data))


def section(title, child, action=None):
    """Heading with an optional "Show All" button above `child`."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    header = Gtk.Box(spacing=6)
    label = Gtk.Label(label=title, xalign=0, hexpand=True,
                      ellipsize=Pango.EllipsizeMode.END)
    label.add_css_class("title-4")
    header.append(label)
    if action:
        button = Gtk.Button(label="Show All", valign=Gtk.Align.CENTER)
        button.add_css_class("flat")
        button.connect("clicked", lambda *_: action())
        header.append(button)
    box.append(header)
    box.append(child)
    return box
