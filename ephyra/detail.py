"""An item's page: backdrop, facts, Play/Resume, overview, and its seasons,
episodes, tracks or children."""
from datetime import datetime

from gi.repository import Adw, GLib, Gtk, Pango

from ephyra import images, text, widgets

CONTAINERS = ("BoxSet", "Folder", "CollectionFolder", "Playlist")


def _label(css=(), **props):
    label = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                      **props)
    for c in css:
        label.add_css_class(c)
    return label


def _dimmed(label):
    label.add_css_class("dimmed")
    label.add_css_class("dim-label")
    return label


class DetailPage(Adw.NavigationPage):
    def __init__(self, window, item):
        super().__init__(title=item.get("Name", ""))
        self.window = window
        self.item = item
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(widgets.loading_page(), "loading")
        view = Adw.ToolbarView(content=self.stack)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)
        self.load()

    def load(self):
        conn = self.window.connection
        jellyfin = conn.jellyfin
        item_id = self.item["Id"]
        kind = self.item.get("Type")

        def fetch():
            item = jellyfin.item(item_id)
            children = []
            if kind == "Series":
                children = jellyfin.seasons(item_id)
            elif kind == "Season":
                children = jellyfin.episodes(item["SeriesId"], item_id)
            elif kind == "MusicAlbum" or kind in CONTAINERS or item.get("IsFolder"):
                children = jellyfin.items(item_id, limit=200)["Items"]
            next_up = jellyfin.next_up(1, item_id) if kind == "Series" else []
            return item, children, next_up

        conn.call(fetch, self._on_loaded)

    def _on_loaded(self, result, error):
        for name in ("content", "error"):
            old = self.stack.get_child_by_name(name)
            if old:
                self.stack.remove(old)
        if error is not None:
            self.stack.add_named(widgets.error_page(
                "Can't Load This", str(error), self.load), "error")
            self.stack.set_visible_child_name("error")
            return
        self.item, children, next_up = result
        self.set_title(self.item.get("Name", ""))
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      child=self._build(children, next_up))
        self.stack.add_named(scrolled, "content")
        self.stack.set_visible_child_name("content")

    # --- layout --------------------------------------------------------

    def _build(self, children, next_up):
        item = self.item
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        ref = images.backdrop(item)
        if ref and item.get("Type") != "Season":
            art = widgets.Artwork(16 / 9, max_height=360)
            fade = Gtk.Box()
            fade.add_css_class("ephyra-backdrop-fade")
            art.add_overlay(fade)
            art.show(self.window.images, ref, 960, widgets.icon_for(item))
            clamp = Adw.Clamp(maximum_size=1100, child=art, tightening_threshold=1100)
            outer.append(clamp)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_start=12, margin_end=12, margin_top=12,
                      margin_bottom=24)
        outer.append(Adw.Clamp(maximum_size=900, child=box))

        if item.get("Type") == "Episode" and item.get("SeriesName"):
            series = Gtk.Button(label=item["SeriesName"], halign=Gtk.Align.START)
            series.add_css_class("flat")
            series.connect("clicked", lambda *_: self.window.show_item(
                {"Id": item["SeriesId"], "Type": "Series",
                 "Name": item["SeriesName"]}))
            box.append(series)
        box.append(_label(("title-1",), label=item.get("Name", "")))
        facts = text.facts(item)
        if facts:
            box.append(_dimmed(_label(label=facts)))
        if item.get("MediaType") in ("Video", "Audio"):
            box.append(self._play_buttons(item))
        if item.get("Taglines"):
            box.append(_label(("heading",), label=item["Taglines"][0]))
        if item.get("Overview"):
            box.append(_label(label=item["Overview"], selectable=False))
        if item.get("Genres"):
            box.append(_dimmed(_label(("caption",), label=", ".join(item["Genres"]))))

        kind = item.get("Type")
        if kind == "Series":
            if next_up:
                box.append(self._section("Next Up", self._rows(next_up, episode=True)))
            if children:
                box.append(self._section("Seasons", self._rows(children)))
        elif kind == "Season" and children:
            box.append(self._section("Episodes", self._rows(children, episode=True)))
        elif kind == "MusicAlbum" and children:
            box.append(self._section("Tracks", self._rows(children, track=True)))
        elif children:
            flow = widgets.card_box(self.window.images, children,
                                    self.window.show_item)
            box.append(self._section("Items", flow))
        return outer

    def _play_buttons(self, item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        row = Gtk.Box(spacing=12)
        resume = text.resume_seconds(item)
        play = Gtk.Button(halign=Gtk.Align.START)
        play.add_css_class("pill")
        play.add_css_class("suggested-action")
        content = Adw.ButtonContent(icon_name="media-playback-start-symbolic",
                                    label=f"Resume {text.clock(resume)}"
                                    if resume else "Play")
        play.set_child(content)
        play.connect("clicked", lambda *_: self.window.play(self.item, resume))
        row.append(play)
        if resume:
            restart = Gtk.Button(icon_name="view-refresh-symbolic",
                                 valign=Gtk.Align.CENTER,
                                 tooltip_text="Play from Start")
            restart.update_property([Gtk.AccessibleProperty.LABEL],
                                    ["Play from Start"])
            restart.add_css_class("circular")
            restart.connect("clicked", lambda *_: self.window.play(self.item, 0))
            row.append(restart)
        data = item.get("UserData") or {}
        row.append(self._toggle("object-select-symbolic", "Mark as Played",
                                "Mark as Unplayed", data.get("Played", False),
                                self.window.connection.jellyfin.set_played))
        row.append(self._toggle("emblem-favorite-symbolic", "Add to Favorites",
                                "Remove from Favorites",
                                data.get("IsFavorite", False),
                                self.window.connection.jellyfin.set_favorite))
        box.append(row)
        if resume:
            bar = Gtk.ProgressBar(fraction=text.played_fraction(item))
            box.append(bar)
        ends = text.ends_at(item, datetime.now(), resume)
        if ends and item.get("MediaType") == "Video":
            box.append(_dimmed(_label(("caption",), label=ends)))
        return box

    def _toggle(self, icon, on_label, off_label, active, call):
        button = Gtk.ToggleButton(icon_name=icon, active=active,
                                  valign=Gtk.Align.CENTER)
        button.add_css_class("circular")

        def label():
            tip = off_label if button.get_active() else on_label
            button.set_tooltip_text(tip)
            button.update_property([Gtk.AccessibleProperty.LABEL], [tip])

        def toggled(*_):
            label()
            state = button.get_active()

            def done(result, error):
                if error is not None:
                    self.window.toast(str(error))
                    button.handler_block(handler)
                    button.set_active(not state)
                    button.handler_unblock(handler)
                    label()
            self.window.connection.call(call, done, self.item["Id"], state)

        label()
        handler = button.connect("toggled", toggled)
        return button

    def _section(self, title, child):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=12)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("title-4")
        box.append(label)
        box.append(child)
        return box

    def _rows(self, items, episode=False, track=False):
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        for child in items:
            listbox.append(self._row(child, episode, track))
        return listbox

    def _row(self, child, episode, track):
        name = child.get("Name", "")
        if (episode or track) and child.get("IndexNumber") is not None:
            name = f"{child['IndexNumber']}. {name}"
        if episode and child.get("SeriesName") and self.item.get("Type") == "Series":
            name = f"{text.episode_code(child)} · {child.get('Name', '')}"
        row = Adw.ActionRow(title=GLib.markup_escape_text(name),
                            activatable=True, title_lines=2)
        sub = text.duration(child.get("RunTimeTicks")) if (episode or track) \
            else text.subtitle(child)
        if sub:
            row.set_subtitle(GLib.markup_escape_text(sub))
        if not track:
            ratio = 16 / 9 if episode else 2 / 3
            art = widgets.Artwork(ratio)
            width = 96 if episode else 40
            art.set_size_request(width, -1)
            art.set_valign(Gtk.Align.CENTER)
            art.set_margin_top(6)
            art.set_margin_bottom(6)
            art.show(self.window.images, images.primary(child), width,
                     widgets.icon_for(child))
            row.add_prefix(art)
        data = child.get("UserData") or {}
        if data.get("Played"):
            check = Gtk.Image(icon_name="object-select-symbolic",
                              tooltip_text="Played")
            check.update_property([Gtk.AccessibleProperty.LABEL], ["Played"])
            check.add_css_class("accent")
            row.add_suffix(check)
        if episode or track:
            play = Gtk.Button(icon_name="media-playback-start-symbolic",
                              valign=Gtk.Align.CENTER, tooltip_text="Play")
            play.update_property([Gtk.AccessibleProperty.LABEL], [f"Play {name}"])
            play.add_css_class("flat")
            play.add_css_class("circular")
            play.connect("clicked", lambda *_: self.window.play(
                child, text.resume_seconds(child)))
            row.add_suffix(play)
        if track:
            row.connect("activated", lambda *_: self.window.play(child, 0))
        else:
            row.connect("activated", lambda *_: self.window.show_item(child))
        return row

    def refresh(self):
        self.load()
