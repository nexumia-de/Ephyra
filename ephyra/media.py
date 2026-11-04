"""Media playback with GStreamer's playbin and gtk4paintablesink
(docs/playback.md).

Gtk.MediaFile can't be used: in GTK 4.20 (GNOME 51 runtime) its
GStreamer backend reads the URI through GIO (giostreamsrc), and the
Flatpak has no gvfs for http://, so the player got no data ("No input
stream provided by subclass", seen on the phone 2026-11-04). playbin
opens the proxy URL itself (souphttpsrc, hlsdemux).

The object offers the part of the GtkMediaStream API the player uses:
properties playing, prepared, ended, timestamp and duration (µs),
seekable, error, and the methods play, pause, set_playing, seek, stop.
"""
import logging

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, GObject, Gst  # noqa: E402

log = logging.getLogger("ephyra.media")

_initialized = False


def init():
    global _initialized
    if not _initialized:
        Gst.init(None)
        _initialized = True


def video_sink():
    """(sink element, Gdk.Paintable or None). gtk4paintablesink from
    gst-plugins-rs is in the GNOME runtime; inside glsinkbin it gets GL
    textures. Without it (some hosts, CI) frames are dropped."""
    init()
    sink = Gst.ElementFactory.make("gtk4paintablesink", None)
    if sink is None:
        log.info("gtk4paintablesink missing, video is not shown")
        return Gst.ElementFactory.make("fakesink", None), None
    paintable = sink.props.paintable
    context = paintable.props.gl_context if hasattr(paintable.props, "gl_context") else None
    if context is not None:
        glsink = Gst.ElementFactory.make("glsinkbin", None)
        if glsink is not None:
            glsink.props.sink = sink
            return glsink, paintable
    return sink, paintable


class Media(GObject.Object):
    __gtype_name__ = "EphyraMedia"

    playing = GObject.Property(type=bool, default=False)
    prepared = GObject.Property(type=bool, default=False)
    ended = GObject.Property(type=bool, default=False)
    seekable = GObject.Property(type=bool, default=False)
    timestamp = GObject.Property(type=GObject.TYPE_INT64, default=0)
    duration = GObject.Property(type=GObject.TYPE_INT64, default=0)
    error = GObject.Property(type=str, default="")

    def __init__(self, uri, video=True):
        super().__init__()
        init()
        self.pipeline = Gst.ElementFactory.make("playbin3", None) or \
            Gst.ElementFactory.make("playbin", None)
        self.pipeline.props.uri = uri
        self._name = self.pipeline.get_name()
        self.paintable = None
        if video:
            sink, self.paintable = video_sink()
        else:
            sink = Gst.ElementFactory.make("fakesink", None)
        self.pipeline.props.video_sink = sink
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        self._bus_handler = bus.connect("message", self._on_message)
        self._tick = GLib.timeout_add(250, self._update_position)
        # No pausing on BUFFERING messages: with hlsdemux2 that left the
        # pipeline stuck after the start-up buffering (tested 2026-11-04);
        # the demuxer's own queues ride out short network stalls.

    # --- GtkMediaStream-like API -------------------------------------

    def get_playing(self):
        return self.playing

    def is_prepared(self):
        return self.prepared

    def get_ended(self):
        return self.ended

    def is_seekable(self):
        return self.seekable

    def get_timestamp(self):
        return self.timestamp

    def get_duration(self):
        return self.duration

    def get_error(self):
        return self.error or None

    def play(self):
        self.set_playing(True)

    def pause(self):
        self.set_playing(False)

    def set_playing(self, playing):
        """Like GtkMediaStream, "playing" is the requested state; it turns
        false by itself at the end or on an error."""
        if playing and self.ended:
            self.ended = False
        state = Gst.State.PLAYING if playing else Gst.State.PAUSED
        if self.pipeline.set_state(state) == Gst.StateChangeReturn.FAILURE:
            self._fail("Can\u2019t start playback")
            return
        if playing != self.playing:
            self.playing = playing

    def seek(self, timestamp):
        """Seek to `timestamp` µs."""
        self.pipeline.seek_simple(
            Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            max(0, timestamp) * Gst.USECOND)
        self.timestamp = max(0, timestamp)

    def stop(self):
        if self._tick:
            GLib.source_remove(self._tick)
            self._tick = 0
        bus = self.pipeline.get_bus()
        if self._bus_handler:
            bus.disconnect(self._bus_handler)
            bus.remove_signal_watch()
            self._bus_handler = 0
        self.pipeline.set_state(Gst.State.NULL)
        if self.playing:
            self.playing = False

    # --- bus -----------------------------------------------------------

    def _fail(self, message):
        log.warning("playback: %s", message)
        if self.playing:
            self.playing = False
        self.error = message

    def _on_message(self, bus, message):
        kind = message.type
        if kind == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            log.debug("gst error: %s (%s)", error.message, debug)
            self._fail(error.message)
        elif kind == Gst.MessageType.EOS:
            self.ended = True
            if self.playing:
                self.playing = False
        elif kind in (Gst.MessageType.DURATION_CHANGED, Gst.MessageType.ASYNC_DONE,
                      Gst.MessageType.STATE_CHANGED):
            self._update_state()

    def _query_duration(self):
        ok, value = self.pipeline.query_duration(Gst.Format.TIME)
        if ok and value > 0 and value // Gst.USECOND != self.duration:
            self.duration = value // Gst.USECOND

    def _query_seekable(self):
        query = Gst.Query.new_seeking(Gst.Format.TIME)
        if self.pipeline.query(query):
            seekable = query.parse_seeking()[1]
            if seekable != self.seekable:
                self.seekable = seekable

    def _update_state(self):
        """prepared and duration from the pipeline's current state, read
        directly instead of from STATE_CHANGED messages: with playbin3 and
        hlsdemux2 the bus delivered only NULL -> READY although the
        pipeline played (2026-11-04)."""
        state = self.pipeline.get_state(0)[1]
        if state in (Gst.State.PAUSED, Gst.State.PLAYING) and not self.prepared:
            self._query_duration()
            self._query_seekable()
            self.prepared = True
        elif self.prepared and not self.duration:
            self._query_duration()
        if (self.ended or self.error) and self.playing:
            self.playing = False

    def _update_position(self):
        self._update_state()
        ok, value = self.pipeline.query_position(Gst.Format.TIME)
        if ok and value >= 0:
            position = value // Gst.USECOND
            if abs(position - self.timestamp) >= 100_000:
                self.timestamp = position
        return GLib.SOURCE_CONTINUE
