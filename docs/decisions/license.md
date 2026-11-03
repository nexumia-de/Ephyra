---
type: Decision Record
title: AGPL-3.0 license
description: Ephyra is AGPL-3.0-or-later like Cirro, with the same contributor terms.
tags: [decision, license]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Status

Accepted (2026-11-03), following the owner's choice for Cirro.

# Decision

`AGPL-3.0-or-later`, contributions under the terms in
`CONTRIBUTING.md` (the author may relicense). AppStream metadata and
the demo library are CC0-1.0.

# Consequences

No GPL-2.0-only code from Jellyfin's repositories may be copied in
(AGPL-3.0 can't include it); Ephyra talks to Jellyfin only over its
HTTP API.
