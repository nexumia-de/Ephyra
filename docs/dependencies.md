---
type: Reference
title: Bundled dependencies
description: Ephyra bundles no third-party module; everything it uses comes from the GNOME runtime.
tags: [dependencies, licensing, flatpak]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Rules

The shared rules are in
[../../phosh-toolkit/docs/licensing.md](../../phosh-toolkit/docs/licensing.md).
CI fails if a module of `de.nexumia.Ephyra.yml` is missing here or
installs no licence files.

# Modules

None. The manifest has only the app module `ephyra`.

# From the runtime (not bundled)

`org.gnome.Platform//51` provides everything Ephyra imports: Python 3
and PyGObject, GTK 4 with its GStreamer media backend, libadwaita,
libsoup 3 with glib-networking (GnuTLS) for mutual TLS, libsecret,
GStreamer and its plugins. Flathub distributes the runtime under its own
terms.

# Not used

No code or assets from Jellyfin's repositories (GPL-2.0) are in Ephyra.
API facts were read from the server source; the accent colour value
`#00a4dc` is taken from jellyfin-web's palette (a fact, not code).
