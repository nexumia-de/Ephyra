---
type: Decision Record
title: Python and PyGObject
description: Ephyra is written in Python with PyGObject, like Cirro; libsoup 3 for HTTP and mutual TLS, GTK's GStreamer backend for playback.
tags: [decision, language, python]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Status

Accepted (2026-11-03).

# Decision

Python 3 with PyGObject: GTK 4, libadwaita, libsoup 3, libsecret,
everything from the GNOME runtime, so the Flatpak bundles nothing. Build
with meson, tests with pytest. Same stack as Cirro, so knowledge and
later shared code carry over.

# Consequences

- No compile step; quick screenshots.
- HTTP goes through libsoup, not Python's `ssl`, because GIO loads
  PKCS #12 client certificates and Python's stdlib can't.
- Video decoding is GStreamer's (C); Python only drives the UI and the
  local proxy, which copies 64 KiB chunks.
