"""Text subtitles drawn by Ephyra over the video: the chosen track is
fetched as SRT and shown in a label, updated from the pipeline's
position (docs/playback.md#audio-and-subtitles)."""
import logging

from gi.repository import GLib, Gtk

from ephyra import playback, subtitles

log = logging.getLogger("ephyra.player")

EVERY = 100   # ms between updates
MARGIN = {False: 24, True: 104}   # below the video, above the controls


class SubtitleView:
    """`position()` gives the playing position in µs (or None), `toast`
    shows a message."""

    def __init__(self, call, jellyfin, position, toast):
        self._call = call
        self._jellyfin = jellyfin
        self._position = position
        self._toast = toast
        self.track = None
        self._timer = 0
        self._wanted = None
        self.label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER,
                               halign=Gtk.Align.CENTER, valign=Gtk.Align.END,
                               margin_start=12, margin_end=12,
                               margin_bottom=MARGIN[False],
                               can_target=False, visible=False)
        for css in ("osd", "title-4", "ephyra-subtitle"):
            self.label.add_css_class(css)

    def set_controls_visible(self, visible):
        self.label.set_margin_bottom(MARGIN[visible])

    def load(self, stream):
        """Fetch the subtitle `stream` has chosen, or clear it."""
        self.track = None
        self.label.set_visible(False)
        path = stream.subtitle_path if stream else None
        self._wanted = (stream, stream.subtitle_index) if stream else None
        if not path:
            if stream and (stream.subtitle_index or -1) >= 0:
                log.debug("subtitle %s: nothing to fetch (%s)",
                          stream.subtitle_index,
                          playback.subtitle_method(stream.source,
                                                   stream.subtitle_index))
            return
        wanted = self._wanted
        jellyfin = self._jellyfin
        log.debug("subtitle %s: fetching %s", stream.subtitle_index, path)

        def fetch():
            return subtitles.Track(subtitles.parse_srt(jellyfin.text(path)))

        def done(track, error):
            if self._wanted != wanted or stream.subtitle_index != wanted[1]:
                return
            if error is not None:
                log.warning("subtitles: %s", error)
                self._toast("Can’t load the subtitles")
                return
            log.debug("subtitle %s: %d cues", wanted[1], len(track.cues))
            if not track.cues:
                self._toast("The subtitles are empty")
            self.track = track
            if not self._timer:
                self._timer = GLib.timeout_add(EVERY, self._update)
        self._call(fetch, done)

    def stop(self):
        """No more subtitles (the player closed)."""
        self._wanted = None
        self.track = None
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self.label.set_visible(False)

    def _update(self):
        if self.track is None:
            self._timer = 0
            self.label.set_visible(False)
            return GLib.SOURCE_REMOVE
        position = self._position()
        shown = self.track.at(position / 1_000_000) if position is not None else ""
        if shown != self.label.get_label():
            self.label.set_markup(shown)
        self.label.set_visible(bool(shown))
        return GLib.SOURCE_CONTINUE
