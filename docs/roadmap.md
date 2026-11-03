---
type: Plan
title: Roadmap
description: Goals and exit criteria of Ephyra's milestones; the work items are GitHub issues in those milestones.
tags: [plan, roadmap, milestones]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# How the plan is tracked

Work items are [issues](https://github.com/nexumia-de/ephyra/issues),
grouped by [milestones](https://github.com/nexumia-de/ephyra/milestones)
and `area: …` labels; issues without a milestone are the backlog. This
file keeps only the goals. Workflow: the toolkit's
[planning with issues and milestones](../../phosh-toolkit/docs/planning.md).

# M0 – Scaffold, connection and playback (done in the first pull request)

App skeleton with metadata, Flatpak manifest, CI and tests; sign-in
with the home/remote route and client certificates
([connection](connection.md)); home, libraries, search, details,
player with resume and progress reports ([playback](playback.md));
Jellyfin look ([design](design.md)).

# M1 – On the phone

**Goal**: Ephyra is the owner's daily Jellyfin client on the phone.

**Exit criteria**: first release installed from the shared repository;
home/remote switching and the client certificate work against the
owner's server; codecs, hardware decoding, CPU and battery measured
for a 1080p movie and the default qualities set from it.

# M2 – Watching comfort

**Goal**: what a daily client needs beyond playing.

**Exit criteria**: subtitles and audio track choice, next episode at
the end of an episode, sorting and filters in libraries, servers with a
private CA, release notes in the About dialog.

# Risks

- **Codecs in the runtime**: if H.264/HEVC are not decoded on the phone,
  every video needs server transcoding; *Convert on the Server* covers
  it, but the defaults may need to change.
- **Python proxy throughput** for high-bitrate files on aarch64.
- **NetworkManager access** from the Flatpak (`--system-talk-name`) is
  a permission Flathub would question; the fallback (local first with
  server id check) still works without it.
