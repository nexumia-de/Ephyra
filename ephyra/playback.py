"""What the player asks the server for: the device profile (which formats
GStreamer plays directly) and the stream path chosen from the server's
PlaybackInfo answer (docs/playback.md). No GTK."""
import logging
import uuid
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

log = logging.getLogger("ephyra.playback")

DIRECT_PLAY = "DirectPlay"
DIRECT_STREAM = "DirectStream"
TRANSCODE = "Transcode"

# Formats the GNOME runtime's GStreamer plays; H.264/HEVC need the codecs
# the runtime provides (docs/playback.md, verify on the phone). TrueHD and
# DTS (Jellyfin calls DTS-HD "dts" too) are decoded by avdec_truehd and
# avdec_dca, both in the GNOME 51 runtime; without them most Blu-ray
# remuxes could not be played directly.
VIDEO_CONTAINERS = "mp4,m4v,mkv,webm,mov"
VIDEO_CODECS = "h264,hevc,vp8,vp9,av1"
AUDIO_CODECS = "aac,mp3,opus,vorbis,flac,ac3,eac3,alac,truehd,dts"
AUDIO_CONTAINERS = "mp3,flac,ogg,oga,opus,m4a,aac,wav,webma"


def device_profile(max_bitrate):
    bitrate = max_bitrate or 140_000_000
    return {
        "Name": "Ephyra",
        "MaxStreamingBitrate": bitrate,
        "MaxStaticBitrate": bitrate,
        "MusicStreamingTranscodingBitrate": 320_000,
        "DirectPlayProfiles": [
            {"Type": "Video", "Container": VIDEO_CONTAINERS,
             "VideoCodec": VIDEO_CODECS, "AudioCodec": AUDIO_CODECS},
            {"Type": "Audio", "Container": AUDIO_CONTAINERS},
        ],
        "TranscodingProfiles": [
            {"Type": "Video", "Container": "ts", "VideoCodec": "h264",
             "AudioCodec": "aac,mp3", "Protocol": "hls",
             "Context": "Streaming", "MaxAudioChannels": "2",
             "MinSegments": 1, "BreakOnNonKeyFrames": True},
            {"Type": "Audio", "Container": "mp3", "AudioCodec": "mp3",
             "Protocol": "http", "Context": "Streaming",
             "MaxAudioChannels": "2"},
        ],
        "ContainerProfiles": [],
        "CodecProfiles": [],
        # Text subtitles come as SRT files next to the stream, which
        # Ephyra draws over the video (ephyra/subtitles.py); picture
        # subtitles (PGS, DVD) match no profile, so the server burns them
        # in (StreamBuilder.GetSubtitleProfile, docs/playback.md), but
        # only when the user chooses one (sessions.fetch_stream).
        "SubtitleProfiles": [{"Format": "srt", "Method": "External"}],
    }


def track_title(stream):
    return (stream.get("DisplayTitle") or stream.get("Title")
            or stream.get("Language") or stream.get("Codec") or "Unknown")


def audio_tracks(source):
    """(Jellyfin index, title) of the audio tracks inside the file, in
    file order, which is also GStreamer's order. External audio files are
    left out: they are not in the stream Ephyra plays."""
    return [(s["Index"], track_title(s)) for s in source.get("MediaStreams") or []
            if s.get("Type") == "Audio" and not s.get("IsExternal")
            and "Index" in s]


CONVERTED = " (converted on the server)"


def subtitle_tracks(source):
    """(Jellyfin index, title) of the subtitles the phone can show: as an
    SRT file (External) or burned in by the server (Encode). Burning in
    means the server re-encodes the whole video, so those say so."""
    return [(s["Index"], track_title(s) + (CONVERTED if s.get("DeliveryMethod") == "Encode"
                                           else ""))
            for s in source.get("MediaStreams") or []
            if s.get("Type") == "Subtitle" and "Index" in s
            and s.get("DeliveryMethod") in ("External", "Encode")]


def subtitle_method(source, index):
    for s in source.get("MediaStreams") or []:
        if s.get("Type") == "Subtitle" and s.get("Index") == index:
            return s.get("DeliveryMethod")
    return None


def burns_in_default(info):
    """True when the server's own subtitle pick (asked without
    SubtitleStreamIndex) would be burned into the video: a picture
    subtitle (PGS, DVD, DVB) matches no subtitle profile, so its method is
    Encode, and the server re-encodes the whole video for it. Ephyra then
    asks again with the subtitle off (docs/playback.md)."""
    sources = info.get("MediaSources") or []
    if not sources:
        return False
    index = sources[0].get("DefaultSubtitleStreamIndex")
    return (index is not None and index >= 0
            and subtitle_method(sources[0], index) == "Encode")


class Stream:
    """The chosen media source: `path` (with query) relative to the server
    base URL, and what is reported to the server."""

    def __init__(self, item_id, source, method, path, play_session_id):
        self.item_id = item_id
        self.source = source
        self.method = method
        self.path = path
        self.play_session_id = play_session_id
        self.details = ""
        # The server's choice for this request (the user's language
        # settings, or what Ephyra asked for); None or -1: none.
        self.audio_index = source.get("DefaultAudioStreamIndex")
        self.subtitle_index = source.get("DefaultSubtitleStreamIndex")

    @property
    def media_source_id(self):
        return self.source.get("Id", self.item_id)

    @property
    def audio_position(self):
        """Position of the chosen audio track among the file's audio
        tracks, as GStreamer counts them; None: GStreamer's default."""
        indexes = [index for index, _ in audio_tracks(self.source)]
        return indexes.index(self.audio_index) if self.audio_index in indexes else None

    @property
    def subtitle_path(self):
        """Server path of the chosen subtitle as SRT, without the token,
        or None (off, burned in, or hosted elsewhere)."""
        for s in self.source.get("MediaStreams") or []:
            if (s.get("Type") == "Subtitle" and s.get("Index") == self.subtitle_index
                    and s.get("DeliveryMethod") == "External"
                    and s.get("DeliveryUrl") and not s.get("IsExternalUrl")):
                return without_token(s["DeliveryUrl"])
        return None

    @property
    def duration(self):
        """Seconds, or 0 when the server does not know."""
        return (self.source.get("RunTimeTicks") or 0) / 10_000_000

    def report(self, position, paused=False, event=""):
        payload = {"ItemId": self.item_id,
                   "MediaSourceId": self.media_source_id,
                   "PlaySessionId": self.play_session_id,
                   "PlayMethod": self.method,
                   "PositionTicks": int(position * 10_000_000),
                   "IsPaused": paused,
                   "CanSeek": True}
        if self.audio_index is not None:
            payload["AudioStreamIndex"] = self.audio_index
        if self.subtitle_index is not None:
            payload["SubtitleStreamIndex"] = self.subtitle_index
        if event == "":
            payload["QueueableMediaTypes"] = ["Video", "Audio"]
        return payload

    def stop_report(self, position, failed=False):
        """The /Sessions/Playing/Stopped payload. `failed`: the stream never
        played; the server then leaves the user's resume position and
        played state alone (SessionManager.OnPlaybackStopped)."""
        payload = self.report(position, event="Stopped")
        if failed:
            payload["Failed"] = True
        return payload


class NoPlayableSource(Exception):
    def __init__(self, message, details=""):
        super().__init__(message)
        self.details = details


def describe(info):
    """One line about the server's answer and the file, shown on the
    player's error page so the owner can report it without a terminal:
    "mkv · hevc · eac3 · direct play no · convert not allowed"."""
    sources = info.get("MediaSources") or []
    parts = []
    if sources:
        source = sources[0]
        if source.get("Container"):
            parts.append(source["Container"])
        for kind in ("Video", "Audio"):
            stream = next((m for m in source.get("MediaStreams") or []
                           if m.get("Type") == kind), None)
            if stream and stream.get("Codec"):
                parts.append(stream["Codec"])
        parts.append("direct play " + ("yes" if source.get("SupportsDirectPlay") else "no"))
        parts.append("convert " + ("allowed" if source.get("SupportsTranscoding") else "not allowed"))
        parts.append("converted stream " + ("offered" if source.get("TranscodingUrl") else "none"))
    else:
        parts.append("no media source")
    if info.get("ErrorCode"):
        parts.append(f"error {info['ErrorCode']}")
    return " · ".join(parts)


def choose(item, info, device_id, token):
    """A Stream for `item` from the PlaybackInfo answer `info`."""
    sources = info.get("MediaSources") or []
    details = describe(info)
    if not sources:
        error = info.get("ErrorCode") or "No playable media"
        raise NoPlayableSource(_error_text(error), details)
    source = sources[0]
    log.debug("PlaybackInfo: DirectPlay %s, DirectStream %s, Transcoding %s, "
              "TranscodingUrl %s, ErrorCode %s",
              source.get("SupportsDirectPlay"), source.get("SupportsDirectStream"),
              source.get("SupportsTranscoding"), bool(source.get("TranscodingUrl")),
              info.get("ErrorCode"))
    session = info.get("PlaySessionId") or uuid.uuid4().hex
    media = "Audio" if item.get("MediaType") == "Audio" else "Videos"
    item_id = item["Id"]
    if source.get("SupportsDirectPlay") or source.get("SupportsDirectStream"):
        method = DIRECT_PLAY if source.get("SupportsDirectPlay") else DIRECT_STREAM
        query = {"static": "true", "mediaSourceId": source.get("Id", item_id),
                 "deviceId": device_id, "playSessionId": session}
        if source.get("ETag"):
            query["tag"] = source["ETag"]
        if source.get("LiveStreamId"):
            query["liveStreamId"] = source["LiveStreamId"]
        path = f"/{media}/{quote(item_id)}/stream?{urlencode(query)}"
        stream = Stream(item_id, source, method, path, session)
        stream.details = details
        return stream
    if source.get("TranscodingUrl"):
        stream = Stream(item_id, source, TRANSCODE,
                        without_token(source["TranscodingUrl"]), session)
        stream.details = details
        return stream
    if not source.get("SupportsTranscoding"):
        # MediaSourceManager sets this from the user's policy
        # (EnableVideoPlaybackTranscoding, docs/playback.md).
        raise NoPlayableSource(
            "Your Jellyfin user may not have videos converted. In Jellyfin's "
            "dashboard, open Users, choose your user and turn on \u201cAllow "
            "video playback that requires transcoding\u201d.", details)
    raise NoPlayableSource("The server offered no converted stream for this file",
                           details)


def without_token(path):
    """The server path of a TranscodingUrl without the token the server
    puts into it (ApiKey/api_key): the proxy sends it as a header, and
    URLs end up in GStreamer's logs."""
    parts = urlsplit(path)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in ("apikey", "api_key")]
    path = parts.path if parts.path.startswith("/") else "/" + parts.path
    return path + ("?" + urlencode(query) if query else "")


def _error_text(code):
    return {
        "NotAllowed": "Your account may not play this",
        "NoCompatibleStream": "The server can't convert this file for the phone",
        "RateLimitExceeded": "The server is busy, try again later",
    }.get(code, "No playable media")
