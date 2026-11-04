---
type: Concept
title: Playback
description: How Ephyra asks the server what to play (device profile, direct play or HLS transcoding), plays it with GTK's GStreamer backend through a local proxy that adds the token and the client certificate, resumes, and reports progress.
tags: [playback, gstreamer, hls, transcoding, proxy, codecs]
resource: ../ephyra/player.py
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
sources:
  - id: jf-mediainfo
    resource: https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/MediaInfoController.cs
    title: Jellyfin server, MediaInfoController (POST /Items/{id}/PlaybackInfo)
  - id: jf-playstate
    resource: https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/PlaystateController.cs
    title: Jellyfin server, PlaystateController (/Sessions/Playing, Progress, Stopped)
  - id: jf-profile
    resource: https://github.com/jellyfin/jellyfin/blob/master/MediaBrowser.Model/Dlna/DeviceProfile.cs
    title: Jellyfin server, DeviceProfile, DirectPlayProfile, TranscodingProfile
---

# What to play (`playback.py`)

`POST /Items/{id}/PlaybackInfo`[^jf-mediainfo] with a device profile[^jf-profile]:

- **Direct play**: video in mp4/m4v/mkv/webm/mov with H.264, HEVC, VP8,
  VP9 or AV1 and AAC, MP3, Opus, Vorbis, FLAC, AC-3, E-AC-3 or ALAC;
  audio in mp3/flac/ogg/opus/m4a/aac/wav/webm.
- **Transcoding**: HLS (MPEG-TS, H.264 + AAC, stereo) for video, MP3
  for audio.
- **Bitrate**: `MaxStreamingBitrate` from the preferences, separately
  for home (default *Original*) and away (default *4 Mbit/s*), so a
  movie plays untouched on the home Wi-Fi and is converted on mobile
  data.
- Subtitles are switched off (`SubtitleStreamIndex: -1`) until Ephyra
  can show them; otherwise the server would burn them in.

`playback.choose()` takes the first media source: direct play or direct
stream → `/Videos/{id}/stream?static=true&mediaSourceId=…&tag=…`
(`/Audio/…` for audio); otherwise the server's `TranscodingUrl`, with
the `ApiKey`/`api_key` the server puts into it removed (the proxy sends
the token as a header). If the phone can't decode the original, the
player's error page offers **Convert on the Server**, which asks again
with direct play and direct stream disabled and `AllowVideoStreamCopy`
/ `AllowAudioStreamCopy` false, so the server re-encodes both streams
instead of copying a codec the phone failed on into HLS.

**Server side** (read in `Jellyfin.Api/Helpers/MediaInfoHelper.cs` and
`Emby.Server.Implementations/Library/MediaSourceManager.cs`, 10.11):
`SupportsTranscoding` comes from the user's policy
`EnableVideoPlaybackTranscoding` ("Allow video playback that requires
transcoding" in the dashboard), `SupportsDirectStream` from
`EnablePlaybackRemuxing`. Without the first, a file the phone can't play
has no `TranscodingUrl`; Ephyra then says which setting to turn on
instead of a generic error. `EnableDirectPlay: false` works because the
helper clears the source's `SupportsDirectPlay` before the stream
builder checks it. `EPHYRA_DEBUG=1` logs the server's decision
(`PlaybackInfo: DirectPlay …, Transcoding …, TranscodingUrl …`).

**Error page.** "Can't Play This" says in one sentence what to do and
shows a small, selectable details line for reports, e.g. `DirectPlay ·
mkv · hevc · eac3 · direct play yes · convert allowed · converted stream
none · GStreamer: No decoder available for type 'video/x-h265'.`
(`playback.describe`, `player.gst_reason`). The same line is logged as a
warning.

# Local media proxy (`proxy.py`)

GTK plays media with GStreamer (`GtkMediaFile`). GStreamer's HTTP
source and its HLS downloader can't present a client certificate, and
the token must not go into URLs. So the player opens
`http://127.0.0.1:<port>/<secret>/<server path>`:

- a `ThreadingHTTPServer` on 127.0.0.1, random port, a random 32-byte
  path secret (other local programs can't use it);
- each request is forwarded to the **current** route's base URL with the
  `Authorization` header and the client certificate (libsoup, one
  session per thread), `Accept-Encoding: identity` so lengths stay
  right;
- `Range`/`If-Range` go up, `Content-Type`, `Content-Length`,
  `Content-Range`, `Accept-Ranges` come back, the body is streamed in
  64 KiB chunks; seeking works. Without a length (live transcode) the
  connection closes at the end of the body.
- HLS playlists from Jellyfin use relative URLs, so segments go through
  the proxy too.

# Player (`player.py`)

`Gtk.MediaFile` on the proxy URL, shown in a `Gtk.Picture` (audio shows
the album cover instead). Resume: after `prepared` it seeks to the
stored position. Reports to the server[^jf-playstate]: `/Sessions/Playing`
when prepared, `/Progress` every 10 s and on play/pause, `/Stopped` when
the page closes; afterwards the detail and home pages reload to show
the new position. While playing, the app inhibits idle and suspend.
Keys: Space, ←/→ (−10/+30 s), F or F11, Escape.

# Verified (2026-11-03)

- In the cloud container (GTK 4.14, GStreamer 1.24): a 10 s VP8/Vorbis
  WebM served by the demo server plays through the proxy at 360×720;
  the position and the controls update.
- `tests/test_connection.py`: a range request through the proxy over
  mutual TLS returns `206` with the right bytes and `Content-Range`; the
  token is not in the URL; a wrong path secret gets `404`.
- `tests/test_ui.py`: a file the phone can't decode shows "Can't Play
  This" with "Convert on the Server".

# Open, on the phone

- Which codecs the GNOME 51 runtime's GStreamer decodes on the phone,
  and whether H.264/HEVC are hardware-decoded; this decides the right
  default for *Original*. Issue in milestone M1.
- Battery and CPU while playing a 1080p file.

[^jf-mediainfo]: Jellyfin server, MediaInfoController
[^jf-playstate]: Jellyfin server, PlaystateController
[^jf-profile]: Jellyfin server, DeviceProfile
