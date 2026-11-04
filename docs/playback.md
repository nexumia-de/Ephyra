---
type: Concept
title: Playback
description: How Ephyra asks the server what to play (device profile, direct play or HLS transcoding), plays it with GTK's GStreamer backend through a local proxy that adds the token and the client certificate, resumes, and reports progress.
tags: [playback, gstreamer, hls, transcoding, proxy, codecs, audio, subtitles]
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
  - id: jf-streambuilder
    resource: https://github.com/jellyfin/jellyfin/blob/master/MediaBrowser.Model/Dlna/StreamBuilder.cs
    title: Jellyfin server, StreamBuilder.GetSubtitleProfile (Embed, External, Encode)
  - id: jf-streaminfo
    resource: https://github.com/jellyfin/jellyfin/blob/master/MediaBrowser.Model/Dlna/StreamInfo.cs
    title: Jellyfin server, StreamInfo (subtitle DeliveryUrl, start position)
  - id: jf-mediainfohelper
    resource: https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Helpers/MediaInfoHelper.cs
    title: Jellyfin server, MediaInfoHelper (DefaultAudioStreamIndex, DefaultSubtitleStreamIndex, DeliveryMethod per stream)
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
- **Tracks**: `AudioStreamIndex` and `SubtitleStreamIndex` are left out
  at first, so the server picks them from the user's language and
  subtitle settings; the answer names its pick in the media source's
  `DefaultAudioStreamIndex` and `DefaultSubtitleStreamIndex`[^jf-mediainfohelper].
  The player's **Audio and Subtitles** sheet asks again with the user's
  choice (subtitle `-1` is off).
- **Subtitle profile**: `{"Format": "srt", "Method": "External"}` only.
  The server then marks every text subtitle `External` with a
  `DeliveryUrl` `/Videos/{id}/{source}/Subtitles/{index}/0/Stream.srt`,
  converting ASS, WebVTT and embedded ones to SRT; picture subtitles
  (PGS, DVD, DVB) match no profile and fall back to `Encode`, burned
  into a converted stream[^jf-streambuilder]. The `0` is the start
  position: 0 for direct play and for HLS, which keeps timestamps[^jf-streaminfo].

# Audio and subtitles

- **Audio, direct play**: the file holds every track. `ephyra/media.py`
  answers playbin3's stream collection with a `select-streams` event: the
  first video and the chosen audio track, in file order (Jellyfin's
  audio indexes in the same order, external audio files left out).
  Switching sends the event again, without a restart.
- **Audio, converted stream**: HLS carries one audio track, so the
  player asks the server again and goes on from the same position.
- **Text subtitles** are drawn by Ephyra: the SRT is fetched with the
  token as a header (`Jellyfin.text`), parsed into cues
  (`ephyra/subtitles.py`; `<b>`, `<i>`, `<u>` kept, other tags dropped)
  and shown in a label on the `osd` background, updated every 100 ms
  from the pipeline's position, above the controls while they show.
  Switching or turning them off needs no restart and works the same
  for converted streams. Decision: [subtitles in the app](decisions/subtitles-in-app.md).
- **Picture subtitles** (`Encode`): choosing one, or leaving one, asks
  the server again, which converts the video with the subtitle burned in.
- playbin3 selects the first embedded subtitle by itself; the
  `select-streams` answer never includes a text stream, so embedded
  subtitles never show twice.
- Progress reports carry `AudioStreamIndex` and `SubtitleStreamIndex`.

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

# Local media proxy (`phosh_toolkit.proxy`)

GTK plays media with GStreamer (`GtkMediaFile`). GStreamer's HTTP
source and its HLS downloader can't present a client certificate, and
the token must not go into URLs. So the player opens
`http://127.0.0.1:<port>/<secret>/<server path>`:

- a `ThreadingHTTPServer` on 127.0.0.1, random port, a random 32-byte
  path secret (other local programs can't use it);
- each request is forwarded to the **current** route's base URL
  (`Connection.forward`) with the `Authorization` header and the client certificate (libsoup, one
  session per thread), `Accept-Encoding: identity` so lengths stay
  right;
- `Range`/`If-Range` go up, `Content-Type`, `Content-Length`,
  `Content-Range`, `Accept-Ranges` come back, the body is streamed in
  64 KiB chunks; seeking works. Without a length (live transcode) the
  connection closes at the end of the body.
- HLS playlists from Jellyfin use relative URLs, so segments go through
  the proxy too.

# Player (`player.py`, `phosh_toolkit.media`)

GStreamer's `playbin3` (`phosh_toolkit.media.Media`) plays the proxy URL;
video goes to `gtk4paintablesink` (inside `glsinkbin` when it has a GL
context) and its paintable into a `Gtk.Picture`; audio shows the album
cover instead. `Media` offers the part of the `GtkMediaStream` API the
player uses (playing, prepared, ended, timestamp, duration, seekable,
error; play, pause, seek, stop).

**Why not `Gtk.MediaFile`:** in GTK 4.20 (GNOME 51) its GStreamer backend
reads the URI through GIO (`giostreamsrc`). Inside the Flatpak GIO can't
open `http://` (no gvfs), so nothing played, direct or converted: the
phone logged `gtk_gst_media_file_source_setup_cb: assertion 'stream !=
NULL' failed` and `gio_base_src: No input stream provided by subclass`,
then "Failed to pause" (2026-11-04). `playbin3` opens the URL itself
(`souphttpsrc`, `hlsdemux2`). Decision:
[playbin instead of GtkMediaFile](decisions/playbin.md).

Two GStreamer details found while testing: the bus delivered only the
`NULL → READY` state change of `playbin3` with `hlsdemux2` (Python
wrappers of messages from streaming threads don't compare equal to the
pipeline either), so `Media` reads the pipeline state directly every
250 ms; and pausing on `BUFFERING` messages left the pipeline stuck after
`hlsdemux2`'s start-up buffering, so `Media` doesn't.

Resume: after `prepared` it seeks to the stored position. Reports to the
server[^jf-playstate]: `/Sessions/Playing` when prepared, `/Progress`
every 10 s and on play/pause, `/Stopped` when the page closes;
afterwards the detail and home pages reload to show the new position.
While playing, the app inhibits idle and suspend. Taps, double taps,
keys and rotating: [player controls](player-controls.md).

**GStreamer in the phone's runtime** (`gst-inspect-1.0` inside
`de.nexumia.Ephyra.Devel`, GNOME 51 with the `codecs-extra` 26.08
extension, 2026-11-04): `hlsdemux`, `hlsdemux2`, `avdec_h264`,
`avdec_aac`, `avdec_flac`, `gtk4paintablesink`, `glsinkbin`.

# Verified (2026-11-04, owner's phone host, GStreamer 1.28.7)

- Audio and subtitles, headless under phoc: `tests/test_media.py` plays
  `tests/data/media/tracks.mkv` (English and German audio, an embedded
  subtitle) with the German track and no subtitle, then switches to
  English without a restart; the UI test chooses German audio and an
  SRT subtitle from the demo server, the label shows it, "Off" hides it.
- A subtitle file through playbin3's `suburi` was tried first: the
  pipeline then often ignored later `select-streams` events (decodebin3
  "Still have streams to activate"; audio switched in 2 of 8 runs
  without a video sink, 5 of 6 with one; 12 of 12 without the file).
- 360×720, turned, and 1000×700 screenshots of the sheet and the
  subtitles over a colour-bar clip.

# Verified (2026-11-04, cloud container, GStreamer 1.24)

- `tests/test_media.py`: a VP8/Vorbis clip through the demo server and
  the proxy plays, pauses, seeks and ends; undecodable data is an error.
- Locally (not in CI, needs `hlsdemux2` and `openh264enc`): a
  Jellyfin-shaped HLS stream (master → main playlist → `hls1/main/N.ts`,
  H.264 + AAC, with `Content-Length` and chunked) through the proxy plays,
  and seeking to 7 s plays to the end.
- Not testable here: the picture through `gtk4paintablesink` (not
  packaged for Ubuntu 24.04); checked on the phone.

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
[^jf-streambuilder]: Jellyfin server, StreamBuilder
[^jf-streaminfo]: Jellyfin server, StreamInfo
[^jf-mediainfohelper]: Jellyfin server, MediaInfoHelper
