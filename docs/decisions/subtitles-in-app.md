---
type: Decision Record
title: Draw text subtitles in the app
description: Text subtitles come from the server as SRT and Ephyra draws them over the video; GStreamer never plays a subtitle stream, and picture subtitles are burned in by the server.
tags: [decision, playback, subtitles, gstreamer]
generated: { by: claude-code/2.1.311, at: 2026-11-04T15:40:00Z }
---

# Status

Accepted (2026-11-04), for issue #3 after the owner asked for audio and
subtitle choice.

# Context

The server can deliver a subtitle in three ways for Ephyra's player:
embedded in the played file, as a separate file (`External`), or burned
into a converted video (`Encode`). playbin3 can show a separate file
(`suburi`) or an embedded track, but with a subtitle file loaded it
often ignored later stream selections, so the audio track could no
longer be switched ([playback](../playback.md), measured on GStreamer
1.28.7). Embedded tracks are missing from converted HLS streams anyway.

# Decision

- The device profile offers only `srt` as `External`; the server
  converts every text subtitle to SRT.
- Ephyra fetches the SRT and draws the cue under the playback position
  in a label over the video (`ephyra/subtitles.py`, `ephyra/player.py`).
- GStreamer's stream selection never includes a text stream.
- Picture subtitles are burned in by the server (`Encode`).

# Consequences

- Choosing or turning off a text subtitle is instant, with no restart,
  the same for direct play and converted streams, and the subtitles turn
  with the rotated player.
- ASS/SSA styling (positions, colours, karaoke) is lost in the
  conversion to SRT; bold, italic and underline stay.
- Timing follows the pipeline position polled every 100 ms.
- Picture subtitles need server CPU and a converted stream.
