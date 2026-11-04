---
type: Decision Record
title: playbin instead of GtkMediaFile
description: Ephyra plays media with GStreamer's playbin3 and gtk4paintablesink, because GtkMediaFile in GTK 4.20 reads http:// through GIO, which the Flatpak can't.
tags: [decision, playback, gstreamer, gtk]
generated: { by: claude-code/2.1.317, at: 2026-11-04T00:45:00Z }
---

# Status

Accepted (2026-11-04) after the owner's phone could play nothing.

# Context

Ephyra 0.1.0 showed videos with `Gtk.MediaFile` on the local proxy URL.
On the phone (GNOME 51 runtime, GTK 4.20) every file failed with
"Failed to pause"; the log showed GTK's GStreamer backend feeding the
pipeline from a GIO input stream that GIO could not open for `http://`
in the sandbox (no gvfs). The cloud host's GTK 4.14 still handed the URI
to playbin, so the tests passed there.

# Decision

`ephyra/media.Media` drives `playbin3` directly and shows its video
through `gtk4paintablesink` (gst-plugins-rs, part of the runtime) in a
`Gtk.Picture`. It mirrors the `GtkMediaStream` calls the player used.

# Consequences

- The proxy URL is opened by GStreamer's own HTTP source and HLS
  demuxer, as before on the host.
- Ephyra now depends on `gtk4paintablesink` being in the runtime
  (verified on the phone); without it `Media` falls back to a fakesink
  and plays only the sound.
- Audio and subtitle track choice (#3) can use playbin3's stream
  selection later.
