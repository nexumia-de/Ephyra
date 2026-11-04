---
type: Decision Record
title: No automatic burn-in of picture subtitles
description: When the server's default subtitle is a picture subtitle it would burn into the video, Ephyra plays without it; picture subtitles stay selectable and are marked as converted on the server.
tags: [decision, playback, subtitles, transcoding, server-load]
generated: { by: claude-code/2.1.318, at: 2026-11-04T22:00:00Z }
sources:
  - id: jf-streambuilder
    resource: https://github.com/jellyfin/jellyfin/blob/06695fb4942c15c7463c2dc644440d988951ed17/MediaBrowser.Model/Dlna/StreamBuilder.cs
    title: Jellyfin server, StreamBuilder (GetDefaultSubtitleStreamIndex, GetSubtitleProfile)
  - id: jf-mediainfohelper
    resource: https://github.com/jellyfin/jellyfin/blob/06695fb4942c15c7463c2dc644440d988951ed17/Jellyfin.Api/Helpers/MediaInfoHelper.cs
    title: Jellyfin server, MediaInfoHelper (DefaultSubtitleStreamIndex, DeliveryMethod per stream)
---

# Status

Accepted (2026-11-04), after the owner's home server ran out of memory
with four parallel transcodes of one Blu-ray remux.

# Context

Without `SubtitleStreamIndex` in PlaybackInfo the server picks a subtitle
from the user's settings (`GetDefaultSubtitleStreamIndex`[^jf-streambuilder])
and reports it as `DefaultSubtitleStreamIndex`[^jf-mediainfohelper]. A
picture subtitle (PGS, DVD, DVB) matches none of Ephyra's subtitle
profiles, so its delivery method is `Encode`: the server re-encodes the
whole video with libx264 to overlay it, even when the video itself could
be played as it is or stream-copied. On the owner's server
(2026-11-04) that was a 1080p H.264 remux with a default PGS track:
`-codec:v:0 libx264 … [main][sub]overlay`, one ffmpeg per start,
4 cores and 8 GB RAM overloaded.

Options:

1. Follow the server's pick (before): correct subtitles by default, a
   full video re-encode for every remux with a default PGS track.
2. Off when the pick would be burned in, selectable by hand (chosen).
3. Never offer picture subtitles: no way to see them at all.

# Decision

- If the first PlaybackInfo answer's default subtitle has method
  `Encode`, Ephyra asks again with `SubtitleStreamIndex: -1`
  (`sessions.fetch_stream`). PlaybackInfo starts no ffmpeg, so the
  first answer costs only the request.
- Text subtitles chosen by the server stay as they are (SRT, drawn by
  Ephyra; [subtitles in the app](subtitles-in-app.md)).
- Picture subtitles stay in the Audio and Subtitles sheet, titled
  "… (converted on the server)". Choosing one asks the server again and
  burns it in, as before.

# Consequences

- A user whose default is a picture subtitle sees no subtitle at first
  and has to choose it in the sheet.
- The server converts the video only when the user asked for it (a
  picture subtitle, or Convert on the Server), or when the phone can't
  play the file or the bitrate is too high.

[^jf-streambuilder]: Jellyfin server, StreamBuilder
[^jf-mediainfohelper]: Jellyfin server, MediaInfoHelper
