"""The server side of one player's streams: ask the server for a stream,
and tell it to stop that stream again when the player replaces or leaves
it, so a player never leaves a transcode running on the server
(docs/playback.md). No GTK."""
import logging

from ephyra import playback

log = logging.getLogger("ephyra.sessions")


def fetch_stream(jellyfin, item, bitrate, audio=None, subtitle=None, force=False,
                 source=None):
    """PlaybackInfo and the chosen Stream. Without a subtitle choice the
    server picks one from the user's settings; if that pick would be
    burned in, ask again with the subtitle off. PlaybackInfo itself starts
    no ffmpeg (that happens at the first HLS segment), so the first answer
    needs no stopping."""
    info = jellyfin.playback_info(item["Id"], bitrate, audio_index=audio,
                                  subtitle_index=subtitle, force_transcode=force,
                                  media_source_id=source)
    if subtitle is None and playback.burns_in_default(info):
        log.info("default subtitle would be burned in: asking without it")
        info = jellyfin.playback_info(item["Id"], bitrate, audio_index=audio,
                                      subtitle_index=-1, force_transcode=force,
                                      media_source_id=info["MediaSources"][0].get("Id"))
    return playback.choose(item, info, jellyfin.device_id, jellyfin.token)


def stop_on_server(jellyfin, stream, position=0, failed=False):
    """Stopped with the stream's PlaySessionId, which ends its ffmpeg jobs
    (PlaystateController.ReportPlaybackStopped); for a converted stream
    also DELETE /Videos/ActiveEncodings, which does the same without the
    session bookkeeping. Errors are logged, not raised: the other call
    still goes out, and the player goes on either way."""
    try:
        jellyfin.report("Stopped", stream.stop_report(position, failed))
    except Exception as e:  # noqa: BLE001 - network, server, anything
        log.info("stop report: %s", e)
    if stream.method == playback.TRANSCODE:
        try:
            jellyfin.stop_encoding(stream.play_session_id)
        except Exception as e:  # noqa: BLE001
            log.info("stop encoding: %s", e)


class Sessions:
    """Requests streams for one player. Only the newest request counts:
    an answer that arrives after a newer request or after close() is
    stopped on the server right away instead of being played.

    `call(fn, done, *args)` runs fn in a worker and done(result, error)
    on the main loop (Connection.call)."""

    def __init__(self, jellyfin, call):
        self.jellyfin = jellyfin
        self._call = call
        self._wanted = 0
        self.closed = False

    def open(self, done, item, bitrate, audio=None, subtitle=None, force=False,
             replace=None, source=None):
        """Ask for a stream; done(stream, error) unless the answer is stale.
        `replace`: (stream, position, failed) of the stream the player
        leaves. It is stopped on the server first, in the same worker, so
        its transcode ends before the new one can start."""
        self._wanted += 1
        ticket = self._wanted
        jellyfin = self.jellyfin

        def work():
            if replace is not None:
                stop_on_server(jellyfin, *replace)
            return fetch_stream(jellyfin, item, bitrate, audio, subtitle, force, source)

        def arrived(stream, error):
            if ticket != self._wanted or self.closed:
                if stream is not None:
                    log.info("stream answer after the player moved on: stopping %s",
                             stream.play_session_id)
                    self.stop(stream, failed=True)
                return
            done(stream, error)

        self._call(work, arrived)

    def stop(self, stream, position=0, failed=False):
        """Stop `stream` on the server. `failed`: it never played, so the
        user's resume position stays as it is."""
        self._call(stop_on_server, _logged, self.jellyfin, stream, position, failed)

    def close(self):
        """No more streams: answers still on the way get stopped."""
        self.closed = True


def _logged(result, error):
    if error is not None:
        log.info("stop: %s", error)
