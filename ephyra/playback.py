"""What the player asks the server for: the device profile (which formats
GStreamer plays directly) and the stream path chosen from the server's
PlaybackInfo answer (docs/playback.md). No GTK."""
import uuid
from urllib.parse import quote, urlencode

DIRECT_PLAY = "DirectPlay"
DIRECT_STREAM = "DirectStream"
TRANSCODE = "Transcode"

# Formats the GNOME runtime's GStreamer plays; H.264/HEVC need the codecs
# the runtime provides (docs/playback.md, verify on the phone).
VIDEO_CONTAINERS = "mp4,m4v,mkv,webm,mov"
VIDEO_CODECS = "h264,hevc,vp8,vp9,av1"
AUDIO_CODECS = "aac,mp3,opus,vorbis,flac,ac3,eac3,alac"
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
        "SubtitleProfiles": [],
    }


class Stream:
    """The chosen media source: `path` (with query) relative to the server
    base URL, and what is reported to the server."""

    def __init__(self, item_id, source, method, path, play_session_id):
        self.item_id = item_id
        self.source = source
        self.method = method
        self.path = path
        self.play_session_id = play_session_id

    @property
    def media_source_id(self):
        return self.source.get("Id", self.item_id)

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
        if event == "":
            payload["QueueableMediaTypes"] = ["Video", "Audio"]
        return payload


class NoPlayableSource(Exception):
    pass


def choose(item, info, device_id, token):
    """A Stream for `item` from the PlaybackInfo answer `info`."""
    sources = info.get("MediaSources") or []
    if not sources:
        error = info.get("ErrorCode") or "No playable media"
        raise NoPlayableSource(_error_text(error))
    source = sources[0]
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
        return Stream(item_id, source, method, path, session)
    if source.get("SupportsTranscoding") and source.get("TranscodingUrl"):
        path = source["TranscodingUrl"]
        if not path.startswith("/"):
            path = "/" + path
        return Stream(item_id, source, TRANSCODE, path, session)
    raise NoPlayableSource("The server can't convert this file for the phone")


def _error_text(code):
    return {
        "NotAllowed": "Your account may not play this",
        "NoCompatibleStream": "The server can't convert this file for the phone",
        "RateLimitExceeded": "The server is busy, try again later",
    }.get(code, "No playable media")
