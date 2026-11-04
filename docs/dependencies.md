---
type: Reference
title: Bundled dependencies
description: Ephyra bundles only phosh-toolkit's shared package; everything else comes from the GNOME runtime.
tags: [dependencies, licensing, flatpak]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Rules

The shared rules are in
[../../phosh-toolkit/docs/licensing.md](../../phosh-toolkit/docs/licensing.md).
CI fails if a module of `de.nexumia.Ephyra.yml` is missing here or
installs no licence files.

# Modules

| Module | Version | Licence | Licence files |
|---|---|---|---|
| `phosh-toolkit` | commit of nexumia-de/phosh-toolkit (tag `v0.1.0` once it exists) | GPL-3.0-or-later (own code, same author) | `LICENSE` → `/app/share/licenses/<app id>/phosh-toolkit/` |

Only `lib/phosh_toolkit/` is installed: the shared connection and
playback code ([shared connection](../../phosh-toolkit/docs/shared-connection.md)).
GPL-3.0-or-later code may be combined with Ephyra's AGPL-3.0-or-later
(section 13 of both licences).

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
