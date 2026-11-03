---
type: Decision Record
title: Jellyfin look instead of the stock look
description: Ephyra follows Jellyfin's visual style (blue accent, poster cards, backdrops) instead of the toolkit's stock libadwaita look, at the owner's request.
tags: [decision, design, jellyfin]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Status

Accepted (2026-11-03) by the owner in the chat that started the app:
"design rules from Jellyfin, or create some, so their style is used".

# Context

The toolkit's design rules ask for the stock libadwaita look and forbid
overriding the accent colour, so all apps look alike and follow the
system accent. A media client is different: users know Jellyfin's web
and TV apps, and the library is mostly artwork.

# Decision

Ephyra takes Jellyfin's look where it is visible and cheap to keep:
Jellyfin's blue as accent with dark text on it, poster
cards with Jellyfin's played/unplayed indicators, backdrops on detail
pages. Layout, widgets and everything else stay libadwaita's and follow
the toolkit. Rules: [docs/design.md](../design.md).

# Consequences

- The accent ignores the user's system accent colour. Since the same
  day this is the toolkit's rule for every app (one accent per app,
  [decision](../../../phosh-toolkit/docs/decisions/app-accent-colours.md)),
  and light/dark follow the system with a choice in the preferences, so
  Ephyra no longer prefers dark on its own.
- On libadwaita 1.5 hosts (Ubuntu 24.04) the CSS variables don't parse;
  `style.css` repeats the accent as `@define-color` so local screenshots
  look right, and GTK prints parser warnings there.
- Jellyfin's scrolling rows would need horizontal scrolling, which the
  toolkit forbids at 360 px; they become wrapping grids.
- If the owner wants the stock look back, deleting the accent block in
  `style.css` is enough.
