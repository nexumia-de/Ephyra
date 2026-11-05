---
type: Concept
title: Player controls
description: Touch and mouse controls of the video player as phone streaming apps have them - double tap on the sides to seek, big buttons in the middle, a button that turns the player sideways for a portrait phone, the end time, Skip Intro / Skip Credits and the next episode with a countdown.
tags: [player, controls, gestures, touch, rotation, segments, next-episode]
resource: ../ephyra/player.py
generated: { by: claude-code/2.1.318, at: 2026-11-05T08:30:00Z }
sources:
  - id: jf-segments
    resource: https://github.com/jellyfin/jellyfin/blob/4fbb2a239c1527e44e0c99c44853500f6b2514e3/Jellyfin.Api/Controllers/MediaSegmentsController.cs
    title: Jellyfin server, MediaSegmentsController (GET /MediaSegments/{itemId}, 10.10)
  - id: jf-segment-types
    resource: https://github.com/jellyfin/jellyfin/blob/4fbb2a239c1527e44e0c99c44853500f6b2514e3/src/Jellyfin.Database/Jellyfin.Database.Implementations/Enums/MediaSegmentType.cs
    title: Jellyfin server, MediaSegmentType (Unknown, Commercial, Preview, Recap, Outro, Intro)
  - id: jf-tvshows
    resource: https://github.com/jellyfin/jellyfin/blob/4fbb2a239c1527e44e0c99c44853500f6b2514e3/Jellyfin.Api/Controllers/TvShowsController.cs
    title: Jellyfin server, TvShowsController.GetEpisodes (startItemId, isMissing)
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

# End time, skipping and the next episode

Code: `ephyra/segments.py` (rules, no GTK), `ephyra/skipper.py` (what
shows when), `ephyra/upnext.py` (the card), `Window.play_instead`.

- **End time**: "Ends at 22:14" left of the duration in the bottom bar,
  from now plus the remaining time, updated every second (also while
  paused, when the end moves on). Same wording as on the detail page
  (`text.ends_after`).
- **Next Episode** (`media-skip-forward-symbolic`) in the header, top
  right, for an episode that has a next one. It plays it at once.
  The next one comes from `GET /Shows/{seriesId}/Episodes?startItemId=…
  &isMissing=false&limit=2`: the server skips the list up to the given
  episode, so the second item is the next one, across seasons[^jf-tvshows].
  Not `/Shows/NextUp`, which answers the next *unwatched* episode, not the
  one after the episode playing.
- **Skip buttons**: Jellyfin 10.10 lists an item's segments at
  `GET /MediaSegments/{itemId}`[^jf-segments] (filled by segment
  providers such as the intro skipper plugin; empty without one). Types
  `Intro`, `Recap`, `Preview`, `Commercial`, `Outro`[^jf-segment-types]
  get a **Skip Intro / Recap / Preview / Ad / Credits** pill (accent
  colour, bottom right) while the position is inside the segment,
  hidden in its last second; it jumps to the segment's end. `Unknown`
  and segments shorter than 1 s are ignored. Jellyfin 10.9 answers 404,
  which counts as no segments.
- **Up next** (episodes with a next one): from the start of the credits
  (an `Outro` starting in the last quarter) or, without marked credits,
  30 s before the end, a card in the bottom right shows "Next episode in
  10 s", `S2:E1 · Name`, **Play Now** and **Cancel**; the episode's still
  only from 480 px width (at 360 px it pushed the card off the screen).
  It counts down only while playing; at 0, or when the episode ends, the
  next one starts. Cancel hides it and the episode ends as before (the
  player closes). Seeking back before the credits offers it again. While
  the card shows, Skip Credits does not.
- **Changing episodes** replaces the player page in the navigation stack
  without an animation (`AdwNavigationView.replace`), so back leads to
  the page the first episode was started from. The old stream is stopped
  on the server first (as always, [playback](playback.md#stopping-streams-on-the-server-sessionspy)),
  fullscreen stays, and a player turned sideways stays turned. The next
  episode starts at its own resume position.
- The skip pill and the card take taps only while shown (`can_target`),
  like the track sheet below, and sit above the bar while the controls
  show, near the edge otherwise.
- Found while testing: a player created turned inside a landscape window
  kept laying itself out and starved the main loop (idle callbacks never
  ran). The rotation is carried over only while the window is portrait,
  the only case the rotate button is offered in.

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

- 2026-11-05, cloud container (GTK 4.14, libadwaita 1.5, GStreamer
  1.24): `tests/test_ui.py::test_skip_intro_end_time_and_next_episode`
  plays a 30 s clip as a demo episode with an intro and credits: Skip
  Intro jumps past the intro, the end time shows, the card appears at the
  credits, Cancel and seeking back work, the countdown starts S2:E1 in
  place of the player and keeps it turned. `tests/test_segments.py`
  covers the rules and the API calls against the demo server (next
  episode across seasons, none after the last, 404 on old servers).
  Broadway screenshots at 360×720 and 1000×700 of the skip pill and the
  card (the header bar does not show in Broadway screenshots of the
  player, also on `main`).

# Open

- On the phone: the countdown and the switch to the next episode with a
  real server and the intro skipper plugin's segments.
- Real touch on the phone: the 400 ms wait before a side tap shows the
  controls, and whether phoc's touch events reach the gesture as
  `TOUCHSCREEN`.

[^phosh-rotation]: Phosh, rotation manager
[^phosh-monitors]: Phosh, monitor manager
