"""The player: GStreamer plays the local proxy URL (docs/playback.md);
touch controls over the video (docs/player-controls.md), progress
reported to the server."""
import logging

from gi.repository import Adw, Gdk, GLib, Gtk

from phosh_toolkit import route
from phosh_toolkit.media import Media

from ephyra import images, playback, subtitles, text, widgets
from ephyra.rotator import Rotator

log = logging.getLogger("ephyra.player")

REPORT_EVERY = 10      # seconds between progress reports
HIDE_AFTER = 3         # seconds until the controls hide while playing
SKIP_BACK, SKIP_FORWARD = 10, 30
FEEDBACK_MS = 800      # how long the double-tap seek bubble stays
SUBTITLE_EVERY = 100   # ms between subtitle updates
SUBTITLE_MARGIN = {False: 24, True: 104}   # below the video, above the controls


class PlayerPage(Adw.NavigationPage):
    def __init__(self, window, item, start=0, force_transcode=False):
        super().__init__(title=item.get("Name", ""), tag="player")
        self.window = window
        self.conn = window.connection
        self.item = item
        self.start = start
        self.force_transcode = force_transcode
        self.stream = None
        self.media = None
        self.started = False
        self.stopped = False
        self._seeking = False
        self._timers = []
        self._hide_timeout = 0
        self._single_tap = 0
        self._feedback_timeout = 0
        self._streak = (None, 0)    # double-tap seeking: side, seconds so far
        self._rotation_fullscreen = False
        self._inhibit = 0
        self._media_handlers = []
        self.subtitle_track = None
        self._subtitle_timer = 0
        # Track choice: None lets the server pick from the user's
        # language settings, subtitle -1 is off.
        self.audio_index = None
        self.subtitle_index = None
        self.is_video = item.get("MediaType") != "Audio"
        self.proxy = window.proxy

        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN,
                                   hexpand=True, vexpand=True)
        self.picture.add_css_class("ephyra-video")
        self.stack = Gtk.Stack()
        self.stack.add_named(self._loading(), "loading")
        overlay = Gtk.Overlay(child=self.picture)
        self.spinner = widgets.spinner()
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_valign(Gtk.Align.CENTER)
        self.spinner.set_visible(False)
        overlay.add_overlay(self.spinner)
        # Subtitles are drawn here, not by GStreamer (docs/playback.md).
        self.subtitle_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER,
                                        halign=Gtk.Align.CENTER, valign=Gtk.Align.END,
                                        margin_start=12, margin_end=12,
                                        margin_bottom=SUBTITLE_MARGIN[False],
                                        can_target=False, visible=False)
        for css in ("osd", "title-4", "ephyra-subtitle"):
            self.subtitle_label.add_css_class(css)
        overlay.add_overlay(self.subtitle_label)
        self.bubbles = {"back": self._bubble("back"),
                        "forward": self._bubble("forward")}
        for bubble in self.bubbles.values():
            overlay.add_overlay(bubble)
        self.transport = self._transport()
        if self.is_video:
            # Phone players put the big buttons in the middle of the video.
            self.center = Gtk.Revealer(child=self.transport, reveal_child=True,
                                       transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                       halign=Gtk.Align.CENTER,
                                       valign=Gtk.Align.CENTER)
            overlay.add_overlay(self.center)
        else:
            self.center = None
        self.sheet = self._track_sheet()
        overlay.add_overlay(self.sheet)
        self.overlay = overlay
        self.stack.add_named(overlay, "video")

        self.view = Adw.ToolbarView(content=self.stack,
                                    extend_content_to_top_edge=True,
                                    extend_content_to_bottom_edge=True,
                                    top_bar_style=Adw.ToolbarStyle.FLAT,
                                    bottom_bar_style=Adw.ToolbarStyle.FLAT)
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(
            title=item.get("Name", ""),
            subtitle=text.title(item) if item.get("Type") == "Episode" else ""))
        header.add_css_class("osd")
        self.fullscreen_button = Gtk.Button(icon_name="view-fullscreen-symbolic",
                                            tooltip_text="Fullscreen")
        self.fullscreen_button.update_property([Gtk.AccessibleProperty.LABEL],
                                               ["Fullscreen"])
        self.fullscreen_button.connect("clicked", lambda *_: self.toggle_fullscreen())
        header.pack_end(self.fullscreen_button)
        self.rotate_button = Gtk.Button(icon_name="object-rotate-left-symbolic",
                                        visible=self.is_video)
        self.rotate_button.connect("clicked", lambda *_: self.toggle_rotation())
        header.pack_end(self.rotate_button)
        self.tracks_button = Gtk.Button(icon_name="media-view-subtitles-symbolic",
                                        tooltip_text="Audio and Subtitles",
                                        visible=False)
        self.tracks_button.update_property([Gtk.AccessibleProperty.LABEL],
                                           ["Audio and Subtitles"])
        self.tracks_button.connect("clicked", lambda *_: self.open_tracks())
        header.pack_end(self.tracks_button)
        self.view.add_top_bar(header)
        self.view.add_bottom_bar(self._controls())
        self.rotator = Rotator(self.view)
        self.rotator.connect("notify::portrait", self._on_portrait)
        self._update_rotate_button()
        self.set_child(self.rotator)

        # On the overlay, not the picture: taps on the buttons above the
        # video stay with the buttons.
        click = Gtk.GestureClick()
        click.connect("released", self._on_tap)
        overlay.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_: self._show_controls())
        self.view.add_controller(motion)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("hidden", self._on_hidden)
        self._fullscreen_handler = window.connect("notify::fullscreened",
                                                  self._on_fullscreened)
        self.prepare()

    # --- widgets -----------------------------------------------------

    def _loading(self):
        page = widgets.loading_page()
        page.set_title(self.item.get("Name", ""))
        return page

    def _controls(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                      margin_start=6, margin_end=6, margin_bottom=6)
        bar.add_css_class("osd")
        bar.add_css_class("toolbar")
        self.scale = Gtk.Scale(adjustment=Gtk.Adjustment(upper=1,
                                                         step_increment=10),
                               draw_value=False, hexpand=True)
        self.scale.update_property([Gtk.AccessibleProperty.LABEL], ["Position"])
        self.scale.connect("change-value", self._on_scale)
        bar.append(self.scale)
        row = Gtk.CenterBox()
        self.position_label = Gtk.Label(label="0:00")
        self.position_label.add_css_class("numeric")
        self.duration_label = Gtk.Label(label="")
        self.duration_label.add_css_class("numeric")
        row.set_start_widget(self.position_label)
        if not self.is_video:
            row.set_center_widget(self.transport)
        row.set_end_widget(self.duration_label)
        bar.append(row)
        return bar

    def _transport(self):
        """Back, play/pause, forward: large round buttons over the video,
        small flat ones in the bar for audio."""
        buttons = Gtk.Box(spacing=24 if self.is_video else 6)
        self.play_button = self._button("media-playback-start-symbolic", "Play",
                                        self.toggle_play)
        self.play_button.add_css_class("circular")
        buttons.append(self._button("media-seek-backward-symbolic",
                                    f"Back {SKIP_BACK} Seconds",
                                    lambda: self.skip(-SKIP_BACK)))
        buttons.append(self.play_button)
        buttons.append(self._button("media-seek-forward-symbolic",
                                    f"Forward {SKIP_FORWARD} Seconds",
                                    lambda: self.skip(SKIP_FORWARD)))
        if self.is_video:
            buttons.add_css_class("ephyra-transport")
            for button in (buttons.get_first_child(), buttons.get_last_child()):
                button.remove_css_class("flat")
                button.add_css_class("circular")
                button.add_css_class("osd")
                button.set_valign(Gtk.Align.CENTER)
            self.play_button.remove_css_class("flat")
            self.play_button.add_css_class("osd")
            self.play_button.add_css_class("ephyra-play")
        return buttons

    def _bubble(self, side):
        """Feedback for double-tap seeking: arrow and the seconds skipped
        so far, on the side that was tapped."""
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

    def _track_sheet(self):
        """Audio and subtitle choice as a sheet inside the player, not a
        popover: popovers are own surfaces and would not turn with the
        rotated player (docs/player-controls.md)."""
        self.track_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        scrolled = Gtk.ScrolledWindow(child=self.track_list,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True)
        title = Gtk.Label(label="Audio and Subtitles", hexpand=True, xalign=0)
        title.add_css_class("heading")
        close = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Close")
        close.update_property([Gtk.AccessibleProperty.LABEL], ["Close"])
        close.add_css_class("flat")
        close.add_css_class("circular")
        close.connect("clicked", lambda *_: self.close_tracks())
        top = Gtk.Box(spacing=6)
        top.append(title)
        top.append(close)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class("ephyra-sheet")
        box.append(top)
        box.append(scrolled)
        box.set_valign(Gtk.Align.END)
        clamp = Adw.Clamp(child=box, maximum_size=760)
        # Filling the overlay, so a long list scrolls instead of running
        # past the edge (the overlay gives an END child its natural height).
        self.sheet_box = box
        # can_target only while open: closed, the revealer still covers the
        # whole video and took the taps meant for the buttons in the middle
        # (found on the phone, 2026-11-04).
        return Gtk.Revealer(child=clamp, reveal_child=False, valign=Gtk.Align.FILL,
                            transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
                            margin_top=48, can_target=False)

    def _track_group(self, title, tracks, current, callback):
        group = Adw.PreferencesGroup(title=title)
        first = None
        for index, label in tracks:
            check = Gtk.CheckButton(active=index == current, valign=Gtk.Align.CENTER)
            if first is None:
                first = check
            else:
                check.set_group(first)
            check.connect("toggled", lambda b, i=index:
                          b.get_active() and callback(i))
            row = Adw.ActionRow(title=label, activatable_widget=check)
            row.set_title_lines(2)
            row.add_prefix(check)
            group.add(row)
        return group

    def _tracks(self):
        if not self.stream or not self.is_video:
            return [], []
        return (playback.audio_tracks(self.stream.source),
                playback.subtitle_tracks(self.stream.source))

    def _update_tracks_button(self):
        audio, subtitles = self._tracks()
        self.tracks_button.set_visible(len(audio) > 1 or bool(subtitles))

    def open_tracks(self):
        audio, subtitles = self._tracks()
        while child := self.track_list.get_first_child():
            self.track_list.remove(child)
        # Side by side when there is room (landscape), stacked otherwise.
        wide = self.overlay.get_width() >= 600
        self.track_list.set_orientation(Gtk.Orientation.HORIZONTAL if wide
                                        else Gtk.Orientation.VERTICAL)
        self.track_list.set_homogeneous(wide)
        if len(audio) > 1:
            self.track_list.append(self._track_group(
                "Audio", audio, self.stream.audio_index, self.choose_audio))
        if subtitles:
            current = self.stream.subtitle_index
            if current is None or current < 0:
                current = -1
            self.track_list.append(self._track_group(
                "Subtitles", [(-1, "Off")] + subtitles, current,
                self.choose_subtitle))
        self._hide_controls()
        self.sheet.set_can_target(True)
        self.sheet.set_reveal_child(True)

    def close_tracks(self):
        self.sheet.set_can_target(False)
        self.sheet.set_reveal_child(False)

    def choose_audio(self, index):
        stream = self.stream
        if stream is None or index == stream.audio_index:
            return
        self.audio_index = index
        self.close_tracks()
        if stream.method != playback.TRANSCODE:
            # The file has every track: switch inside GStreamer.
            stream.audio_index = index
            if self.media:
                self.media.select_audio(stream.audio_position)
            self._report("Progress")
        else:
            # A converted stream carries one audio track: ask again.
            self._reload()

    def choose_subtitle(self, index):
        stream = self.stream
        if stream is None:
            return
        current = stream.subtitle_index if stream.subtitle_index is not None else -1
        if index == current:
            return
        self.subtitle_index = index
        burned = playback.subtitle_method(stream.source, current) == "Encode"
        wanted = playback.subtitle_method(stream.source, index)
        log.debug("subtitle %s -> %s (%s, burned now %s)", current, index,
                  wanted, burned)
        # The sheet covers the bottom of the video, where the subtitle
        # shows: close it on a choice.
        self.close_tracks()
        if burned or wanted == "Encode":
            # Burned into the picture by the server, or no longer.
            self._reload()
        else:
            stream.subtitle_index = index
            self._load_subtitle()
            self._report("Progress")

    def _load_subtitle(self):
        """Fetch the chosen subtitle as SRT, or clear it."""
        self.subtitle_track = None
        self.subtitle_label.set_visible(False)
        path = self.stream.subtitle_path if self.stream else None
        if not path:
            if self.stream and (self.stream.subtitle_index or -1) >= 0:
                log.debug("subtitle %s: nothing to fetch (%s)",
                          self.stream.subtitle_index,
                          playback.subtitle_method(self.stream.source,
                                                   self.stream.subtitle_index))
            return
        jellyfin = self.conn.jellyfin
        wanted = self.stream.subtitle_index
        log.debug("subtitle %s: fetching %s", wanted, path)

        def fetch():
            return subtitles.Track(subtitles.parse_srt(jellyfin.text(path)))

        def done(track, error):
            if self.stopped or not self.stream or self.stream.subtitle_index != wanted:
                return
            if error is not None:
                log.warning("subtitles: %s", error)
                self.window.toast("Can\u2019t load the subtitles")
                return
            log.debug("subtitle %s: %d cues", wanted, len(track.cues))
            if not track.cues:
                self.window.toast("The subtitles are empty")
            self.subtitle_track = track
            if not self._subtitle_timer:
                self._subtitle_timer = GLib.timeout_add(SUBTITLE_EVERY,
                                                        self._update_subtitle)
        self.conn.call(fetch, done)

    def _update_subtitle(self):
        if self.subtitle_track is None or self.stopped:
            self._subtitle_timer = 0
            self.subtitle_label.set_visible(False)
            return GLib.SOURCE_REMOVE
        shown = ""
        if self.media is not None:
            shown = self.subtitle_track.at(self.media.position_now() / 1_000_000)
        if shown != self.subtitle_label.get_label():
            self.subtitle_label.set_markup(shown)
        self.subtitle_label.set_visible(bool(shown))
        return GLib.SOURCE_CONTINUE

    def _button(self, icon, label, callback):
        button = Gtk.Button(icon_name=icon, tooltip_text=label)
        button.add_css_class("flat")
        button.update_property([Gtk.AccessibleProperty.LABEL], [label])
        button.connect("clicked", lambda *_: callback())
        return button

    # --- start -------------------------------------------------------

    def bitrate(self):
        account = self.conn.account
        return (account.quality_home if self.conn.state == route.LOCAL
                else account.quality_away)

    def prepare(self):
        jellyfin = self.conn.jellyfin
        item = self.item
        bitrate = self.bitrate()
        force = self.force_transcode

        audio, subtitle = self.audio_index, self.subtitle_index

        def fetch():
            info = jellyfin.playback_info(item["Id"], bitrate, audio_index=audio,
                                          subtitle_index=subtitle,
                                          force_transcode=force)
            return playback.choose(item, info, jellyfin.device_id, jellyfin.token)

        self.conn.call(fetch, self._on_stream)

    def _on_stream(self, stream, error):
        if error is not None:
            self._fail(str(error), getattr(error, "details", ""))
            return
        self.stream = stream
        self.audio_index = stream.audio_index
        self.subtitle_index = stream.subtitle_index
        log.info("%s %s", stream.method, stream.path)
        for track in stream.source.get("MediaStreams") or []:
            if track.get("Type") == "Subtitle":
                # Never the DeliveryUrl itself: it carries the token.
                log.debug("subtitle track %s: %s, external file %s, text %s, "
                          "delivery %s, url %s, url elsewhere %s",
                          track.get("Index"), track.get("Codec"),
                          track.get("IsExternal"), track.get("IsTextSubtitleStream"),
                          track.get("DeliveryMethod"), bool(track.get("DeliveryUrl")),
                          track.get("IsExternalUrl"))
        log.debug("chosen: audio %s, subtitle %s", stream.audio_index,
                  stream.subtitle_index)
        if self.item.get("MediaType") == "Audio" and not self._timers:
            self._show_cover()
        self._start_media()
        self._load_subtitle()
        self._update_tracks_button()
        if not self._timers:
            self._timers.append(GLib.timeout_add_seconds(REPORT_EVERY,
                                                         self._report_progress))
        if not self._inhibit:
            self._inhibit = self.window.get_application().inhibit(
                self.window, Gtk.ApplicationInhibitFlags.IDLE |
                Gtk.ApplicationInhibitFlags.SUSPEND, "Playing media")
        self._show_controls()

    def _start_media(self):
        stream = self.stream
        url = self.proxy.url(stream.path)
        # Not Gtk.MediaFile: GTK 4.20 reads http:// through GIO, which
        # the Flatpak can't (phosh_toolkit.media).
        self.media = Media(url, video=self.item.get("MediaType") != "Audio",
                           audio_position=stream.audio_position)
        self._media_handlers = [
            self.media.connect(f"notify::{prop}", self._on_media)
            for prop in ("timestamp", "duration", "playing", "error", "prepared",
                         "ended")]
        if self.item.get("MediaType") != "Audio":
            self.picture.set_paintable(self.media.paintable)
        self.stack.set_visible_child_name("video")
        self.media.play()

    def _reload(self):
        """Ask the server again (other audio in a converted stream, burned
        subtitles on or off) and go on from the current position."""
        self.start = self.position()
        self._stop_media()
        self.started = False
        self.stack.set_visible_child_name("loading")
        self.prepare()

    def _show_cover(self):
        art = widgets.Artwork(1)
        art.show(self.window.images, images.primary(self.item), 360,
                 widgets.icon_for(self.item))
        art.set_halign(Gtk.Align.CENTER)
        art.set_valign(Gtk.Align.CENTER)
        art.set_size_request(240, -1)
        overlay = self.stack.get_child_by_name("video")
        overlay.add_overlay(art)

    def _fail(self, message, details=""):
        """Error page; `details` (file and server answer, see
        playback.describe) is selectable so it can be copied into an
        issue."""
        page = Adw.StatusPage(icon_name="dialog-error-symbolic",
                              title="Can\u2019t Play This", description=message)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        if not self.force_transcode:
            button = Gtk.Button(label="Convert on the Server",
                                halign=Gtk.Align.CENTER)
            button.add_css_class("pill")
            button.add_css_class("suggested-action")
            button.connect("clicked", lambda *_: self._retry_transcoded())
            box.append(button)
        if details:
            label = Gtk.Label(label=details, wrap=True, selectable=True,
                              justify=Gtk.Justification.CENTER)
            label.add_css_class("caption")
            label.add_css_class("dimmed")
            label.add_css_class("dim-label")
            box.append(label)
            log.warning("playback details: %s", details)
        page.set_child(box)
        old = self.stack.get_child_by_name("error")
        if old:
            self.stack.remove(old)
        self.stack.add_named(page, "error")
        self.stack.set_visible_child_name("error")
        self.view.set_reveal_top_bars(True)
        self.view.set_reveal_bottom_bars(False)
        if self.center is not None:
            self.center.set_reveal_child(False)

    def _retry_transcoded(self):
        self._stop_media()
        self.force_transcode = True
        self.started = False
        self.stack.set_visible_child_name("loading")
        self.view.set_reveal_bottom_bars(True)
        self.prepare()

    # --- media state ---------------------------------------------------

    def position(self):
        return self.media.get_timestamp() / 1_000_000 if self.media else 0

    def duration(self):
        if self.media and self.media.get_duration() > 0:
            return self.media.get_duration() / 1_000_000
        return self.stream.duration if self.stream else 0

    def _on_media(self, media, pspec):
        name = pspec.name
        if name == "error" and media.get_error():
            message = media.get_error()
            log.warning("playback: %s", message)
            # GStreamer's message is long and technical: it goes into the
            # copyable details line, the page says what to do.
            details = f"{self.stream.method} · {self.stream.details}" \
                if self.stream else ""
            details = f"{details} · GStreamer: {gst_reason(message)}"
            self._fail("This phone can\u2019t play the file as it is. The "
                       "server can convert it to a format the phone plays.",
                       details)
            return
        if name == "prepared" and media.is_prepared():
            if self.start > 1:
                media.seek(int(self.start * 1_000_000))
            if not self.started:
                self._report("")
                self.started = True
        if name in ("timestamp", "duration", "prepared"):
            duration = self.duration()
            if duration:
                self.scale.get_adjustment().set_upper(duration)
                self.duration_label.set_label(text.clock(duration))
            if not self._seeking:
                self.scale.set_value(self.position())
            self.position_label.set_label(text.clock(self.position()))
        if name in ("playing", "prepared"):
            playing = media.get_playing()
            self.play_button.set_icon_name("media-playback-pause-symbolic"
                                           if playing else
                                           "media-playback-start-symbolic")
            label = "Pause" if playing else "Play"
            self.play_button.set_tooltip_text(label)
            self.play_button.update_property([Gtk.AccessibleProperty.LABEL], [label])
            if self.started:
                self._report("Progress")
            self._show_controls()
        if name == "ended" and media.get_ended():
            self.window.nav.pop()

    # --- controls ------------------------------------------------------

    def toggle_play(self):
        if self.media:
            self.media.set_playing(not self.media.get_playing())

    def skip(self, seconds, show=True):
        if self.media and self.media.is_seekable():
            target = min(max(0, self.position() + seconds), self.duration() or 1e9)
            self.media.seek(int(target * 1_000_000))
        if show:
            self._show_controls()

    def _on_scale(self, scale, scroll, value):
        if self.media and self.media.is_seekable():
            self.media.seek(int(max(0, value) * 1_000_000))
        self._show_controls()
        return False

    def toggle_fullscreen(self):
        if self.window.is_fullscreen():
            self.window.unfullscreen()
        else:
            self.window.fullscreen()

    def _on_fullscreened(self, *_):
        full = self.window.is_fullscreen()
        icon = "view-restore-symbolic" if full else "view-fullscreen-symbolic"
        label = "Leave Fullscreen" if full else "Fullscreen"
        self.fullscreen_button.set_icon_name(icon)
        self.fullscreen_button.set_tooltip_text(label)
        self.fullscreen_button.update_property([Gtk.AccessibleProperty.LABEL],
                                               [label])

    def toggle_rotation(self):
        """Turn the player sideways in a portrait window, and back. Turning
        also goes fullscreen, like a phone app switching to landscape."""
        rotated = not self.rotator.props.rotated
        self.rotator.props.rotated = rotated
        if rotated and not self.window.is_fullscreen():
            self._rotation_fullscreen = True
            self.window.fullscreen()
        elif not rotated and self._rotation_fullscreen:
            self._rotation_fullscreen = False
            if self.window.is_fullscreen():
                self.window.unfullscreen()
        self._update_rotate_button()
        self._show_controls()

    def _on_portrait(self, *_):
        # The display itself turned to landscape (auto-rotate): undo ours.
        if not self.rotator.props.portrait and self.rotator.props.rotated:
            self.toggle_rotation()
        self._update_rotate_button()

    def _update_rotate_button(self):
        rotated = self.rotator.props.rotated
        label = "Rotate Back" if rotated else "Rotate to Landscape"
        self.rotate_button.set_icon_name("object-rotate-right-symbolic" if rotated
                                         else "object-rotate-left-symbolic")
        self.rotate_button.set_tooltip_text(label)
        self.rotate_button.update_property([Gtk.AccessibleProperty.LABEL], [label])
        self.rotate_button.set_visible(self.is_video and
                                       (rotated or self.rotator.props.portrait))

    def _on_tap(self, gesture, n, x, y):
        if self.sheet.get_reveal_child():
            # A tap beside the open track sheet closes it.
            target = self.overlay.pick(x, y, Gtk.PickFlags.DEFAULT)
            if target is None or not (target is self.sheet_box or
                                      target.is_ancestor(self.sheet_box)):
                self.close_tracks()
            return
        device = gesture.get_current_event_device()
        touch = (device is not None and
                 device.get_source() == Gdk.InputSource.TOUCHSCREEN)
        self.tap(n, tap_zone(x, self.overlay.get_width()), touch)

    def tap(self, n, zone, touch):
        """A tap or click on the video, `n` counting quick repeats."""
        if self._single_tap:
            GLib.source_remove(self._single_tap)
            self._single_tap = 0
        action = tap_action(n, zone, touch)
        if action == "wait":
            # Might become a double tap; act once the double-tap time passed.
            delay = Gtk.Settings.get_default().props.gtk_double_click_time
            self._single_tap = GLib.timeout_add(delay, self._on_single_tap, touch)
        elif action in ("back", "forward"):
            self._double_tap_seek(action)
        elif action == "fullscreen":
            self.toggle_fullscreen()
        elif action == "controls":
            self._toggle_controls()

    def _on_single_tap(self, touch):
        self._single_tap = 0
        if touch:
            self._toggle_controls()
        else:
            self.toggle_play()
            self._show_controls()
        return GLib.SOURCE_REMOVE

    def _toggle_controls(self):
        if self.view.get_reveal_bottom_bars():
            self._hide_controls()
        else:
            self._show_controls()

    def _double_tap_seek(self, side):
        seconds = SKIP_BACK if side == "back" else SKIP_FORWARD
        if not (self.media and self.media.is_seekable()):
            return
        self.skip(-seconds if side == "back" else seconds, show=False)
        # The bubble takes the place of the controls, as in phone players.
        self._hide_controls()
        last, total = self._streak
        total = total + seconds if last == side else seconds
        self._streak = (side, total)
        bubble = self.bubbles[side]
        bubble.label.set_label(f"{total} s")
        bubble.set_reveal_child(True)
        other = self.bubbles["forward" if side == "back" else "back"]
        other.set_reveal_child(False)
        if self._feedback_timeout:
            GLib.source_remove(self._feedback_timeout)
        self._feedback_timeout = GLib.timeout_add(FEEDBACK_MS, self._end_feedback)

    def _end_feedback(self):
        self._feedback_timeout = 0
        self._streak = (None, 0)
        for bubble in self.bubbles.values():
            bubble.set_reveal_child(False)
        return GLib.SOURCE_REMOVE

    def _show_controls(self):
        visible = self.stack.get_visible_child_name() != "error"
        self.view.set_reveal_top_bars(True)
        self.view.set_reveal_bottom_bars(visible)
        if self.center is not None:
            self.center.set_reveal_child(visible)
        self.subtitle_label.set_margin_bottom(SUBTITLE_MARGIN[visible])
        self.set_cursor(None)
        if self._hide_timeout:
            GLib.source_remove(self._hide_timeout)
        self._hide_timeout = GLib.timeout_add_seconds(HIDE_AFTER, self._autohide)

    def _autohide(self):
        self._hide_timeout = 0
        if (self.media and self.media.get_playing()
                and self.item.get("MediaType") == "Video"):
            self._hide_controls()
        return GLib.SOURCE_REMOVE

    def _hide_controls(self):
        self.view.set_reveal_top_bars(False)
        self.view.set_reveal_bottom_bars(False)
        if self.center is not None:
            self.center.set_reveal_child(False)
        self.subtitle_label.set_margin_bottom(SUBTITLE_MARGIN[False])
        self.set_cursor(Gdk.Cursor.new_from_name("none"))

    def _on_key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_space:
            self.toggle_play()
        elif keyval == Gdk.KEY_Left:
            self.skip(-SKIP_BACK)
        elif keyval == Gdk.KEY_Right:
            self.skip(SKIP_FORWARD)
        elif keyval in (Gdk.KEY_f, Gdk.KEY_F11):
            self.toggle_fullscreen()
        elif keyval == Gdk.KEY_Escape and self.sheet.get_reveal_child():
            self.close_tracks()
        elif keyval == Gdk.KEY_Escape and self.window.is_fullscreen():
            self.toggle_fullscreen()
        else:
            return False
        return True

    # --- reporting -----------------------------------------------------

    def _report(self, event):
        if not self.stream:
            return
        payload = self.stream.report(self.position(),
                                     paused=not (self.media and self.media.get_playing()),
                                     event=event)
        self.conn.call(self.conn.jellyfin.report, _ignore, event, payload)

    def _report_progress(self):
        if self.started and not self.stopped:
            self._report("Progress")
        return GLib.SOURCE_CONTINUE

    def _stop_media(self, report=True):
        if self.media:
            if self.started and report:
                self._report("Stopped")
            for handler in self._media_handlers:
                self.media.disconnect(handler)
            self._media_handlers = []
            self.media.stop()
            self.media = None
        self.picture.set_paintable(None)

    def _on_hidden(self, *_):
        if self.stopped:
            return
        self.stopped = True
        for timer in self._timers:
            GLib.source_remove(timer)
        for source in (self._hide_timeout, self._single_tap,
                       self._feedback_timeout, self._subtitle_timer):
            if source:
                GLib.source_remove(source)
        self._hide_timeout = self._single_tap = self._feedback_timeout = 0
        self._subtitle_timer = 0
        if self._inhibit:
            self.window.get_application().uninhibit(self._inhibit)
        self.window.disconnect(self._fullscreen_handler)
        if self.window.is_fullscreen():
            self.window.unfullscreen()
        self._stop_media()
        self.window.after_playback(self.item)


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


def gst_reason(message):
    """The readable part of a GStreamer error ("Could not determine type
    of stream."), without element paths and source locations."""
    text = message.split("\n")[0]
    if text.startswith("Error from element") and ": " in text:
        text = text.split(": ", 1)[1]
    for cut in (" ../", " /Gst"):
        index = text.find(cut)
        if index > 0:
            text = text[:index]
    return text.strip() or message[:120]


def _ignore(result, error):
    if error is not None:
        log.info("report: %s", error)

