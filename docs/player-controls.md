---
type: Concept
title: Player controls
description: Touch and mouse controls of the video player as phone streaming apps have them - double tap on the sides to seek, big buttons in the middle, and a button that turns the player sideways for a portrait phone.
tags: [player, controls, gestures, touch, rotation]
resource: ../ephyra/player.py
generated: { by: claude-code/2.1.311, at: 2026-11-04T01:04:00Z }
sources:
  - id: phosh-rotation
    resource: https://gitlab.gnome.org/World/Phosh/phosh/-/blob/main/src/rotation-manager.c
    title: Phosh, rotation manager (orientation lock, monitor transform)
  - id: phosh-monitors
    resource: https://gitlab.gnome.org/World/Phosh/phosh/-/blob/main/src/monitor-manager.c
    title: Phosh, monitor manager (org.gnome.Mutter.DisplayConfig, ApplyMonitorsConfig)
---

# What the controls do

The player follows what phone users know from Netflix, YouTube, Prime
Video and Jellyfin's own Android app, within libadwaita's look:

| Input | Where | Action |
| --- | --- | --- |
| Tap | anywhere | show or hide the controls |
| Double tap | left third | back 10 s; every further quick tap another 10 s |
| Double tap | right third | forward 30 s; every further quick tap another 30 s |
| Double tap | middle | nothing more than the first tap |
| Click (mouse) | anywhere | play or pause |
| Double click (mouse) | anywhere | fullscreen on/off |
| Keys | | Space, ←/→ (−10/+30 s), F or F11, Escape |

- **Big buttons in the middle** (video only): back, play/pause and
  forward as round `osd` buttons (56 and 72 px), shown and hidden
  together with the header and the seek bar. Audio keeps small buttons
  in the bottom bar under the cover.
- **Seek feedback**: a double tap hides the controls and shows a round
  bubble on the tapped side with an arrow and the seconds skipped so far
  ("20 s"); it fades after 0.8 s.
- **Skip lengths** stay at 10 s back and 30 s forward, Jellyfin's
  defaults, the same for buttons, keys and double taps.
- A single tap on the sides waits for GTK's double-click time (400 ms by
  default) so it can still become a double tap; a tap in the middle acts
  at once. The tap gesture is on the overlay, so taps on the buttons stay
  with the buttons.
- Touch and mouse are told apart by the event's input source
  (`Gdk.InputSource.TOUCHSCREEN`). A mouse click plays or pauses as in
  web players; touch never pauses by accident.

# Audio and subtitles

The header's **Audio and Subtitles** button (video only, shown when
there is more than one audio track or any subtitle) opens a sheet
inside the player: radio rows for the audio tracks and for the
subtitles with **Off** first, titled with Jellyfin's `DisplayTitle`
("German - AC3 - 5.1"). Side by side when the player is at least
600 px wide (turned phone, desktop), stacked otherwise; long lists
scroll. A choice, a tap beside the sheet, its close button or Escape
closes it (it covers the bottom of the video, where the subtitle shows).
While closed it takes no taps (`can_target` false): the closed revealer
still covered the whole video and swallowed the taps meant for the
buttons in the middle (owner, on the phone, 2026-11-04;
`tests/test_ui.py` now picks the widget under each button).
While it is open the header bar, the timeline and the buttons in the
middle stay hidden, also when playback events or pointer movement would
show them, and come back when it closes, as in phone players: the bars
are drawn over the video, so they covered the bottom of the sheet
(owner, on the phone, 2026-11-04). libadwaita 1.6's `AdwBottomSheet`
would be the stock widget for this, but the host's libadwaita 1.5 (tests,
screenshots) doesn't have it.
It is a sheet in the player and not a popover, because popovers are
separate surfaces and would not turn with the player. What happens on
a choice: [playback](playback.md#audio-and-subtitles).

# Rotate to landscape

A **Rotate to Landscape** button in the header (video only, shown while
the window is portrait) turns the whole player a quarter clockwise and
goes fullscreen; the phone is then held turned counter-clockwise, as
Android apps do in landscape. **Rotate Back** undoes it and leaves
fullscreen if rotating entered it. If the display itself turns to
landscape (auto-rotate), Ephyra drops its own rotation; in a landscape
window the button is hidden.

`ephyra/rotator.py` allocates the player with a `Gsk.Transform`
(translate by the width, rotate 90°) and swapped width and height. GTK
applies the transform to drawing and to input, so taps, the seek bar
and the double-tap zones work in the turned player
(`tests/test_player.py` checks the corner mapping and picking).

Why not turn the display: Phosh turns outputs only in its rotation
manager, following the accelerometer unless the orientation lock
(`org.gnome.settings-daemon.peripherals.touchscreen orientation-lock`)
is set[^phosh-rotation]; other programs can only change the transform
through `org.gnome.Mutter.DisplayConfig.ApplyMonitorsConfig`[^phosh-monitors].
A Flatpak needs `--talk-name=org.gnome.Mutter.DisplayConfig` for that,
the change is global (it stays if the app crashes) and auto-rotate turns
it back. Decision: [rotate in the app](decisions/rotate-in-app.md).

# Verified (2026-11-04)

- Headless phoc at 360×720 (scale 2) and 1000×700 on the owner's phone
  host with a colour-bar clip: buttons readable over the picture, bubble
  on the tapped side, the turned player fills the screen; at 1000×700
  the rotate button is hidden.
- `tests/test_ui.py`: double tap seeks back and counts up the bubble,
  the controls hide, rotating enters and leaves fullscreen.

- Audio and subtitle sheet at 360×720, turned (two columns) and
  1000×700; the subtitles stay above the controls while they show.

# Open

- Real touch on the phone: the 400 ms wait before a side tap shows the
  controls, and whether phoc's touch events reach the gesture as
  `TOUCHSCREEN`.

[^phosh-rotation]: Phosh, rotation manager
[^phosh-monitors]: Phosh, monitor manager
