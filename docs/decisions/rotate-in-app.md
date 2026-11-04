---
type: Decision Record
title: Rotate the player inside the app
description: The rotate button turns the player widget with a GSK transform instead of turning the display through Phosh's DisplayConfig API.
tags: [decision, player, rotation, phosh, flatpak]
generated: { by: claude-code/2.1.311, at: 2026-11-04T01:04:00Z }
---

# Status

Accepted (2026-11-04), when the owner asked for a button that turns the
picture to landscape.

# Context

Android apps request landscape and the system turns the screen. Phosh
has no such request for apps: it turns the output from its rotation
manager (accelerometer, orientation lock), and other programs can only
change the output transform through
`org.gnome.Mutter.DisplayConfig.ApplyMonitorsConfig`
([player controls](../player-controls.md)).

# Decision

Ephyra turns the player itself: `ephyra/rotator.py` allocates the page
with a quarter-turn transform and swapped size, and the window goes
fullscreen. The button is shown only while the window is portrait.

# Consequences

- No extra Flatpak permission, nothing global changes, and a crash
  leaves the display as it was.
- Phosh's own UI (lock screen, notifications, on-screen keyboard)
  stays portrait while the player is turned.
- The swipe-back gesture follows the screen, not the player: while
  turned it runs along the video's vertical axis.
- Rejected: DisplayConfig from the app (permission Flathub would
  question, fights auto-rotate, global state left behind on a crash).
