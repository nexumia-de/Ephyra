---
type: Decision Record
title: Local media proxy for playback
description: The player plays a 127.0.0.1 URL; a small proxy adds the token and the client certificate and forwards to the current server address.
tags: [decision, playback, proxy, mtls]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Status

Accepted (2026-11-03); details in [playback](../playback.md).

# Context

The remote server requires a client certificate. GStreamer's
`souphttpsrc` has a `tls-interaction` property, but HLS segments are
fetched by `hlsdemux2`'s own downloader, and `GtkMediaFile` gives no
access to either. Jellyfin also accepts the token as `api_key` in URLs,
which would put it into GStreamer's logs and caches.

# Decision

A local HTTP proxy on 127.0.0.1 with a random port and path secret
forwards every media request through Ephyra's own libsoup client.

# Consequences

- Works the same for direct play, HLS, local and remote route; a route
  change between segments is picked up.
- Video bytes pass through Python (one thread per connection, 64 KiB
  chunks); to be measured on the phone with a 1080p file.
