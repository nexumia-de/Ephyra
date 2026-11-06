---
type: Decision Record
title: App name Ephyra
description: The code name is Ephyra, after the young stage of a jellyfish; app id de.nexumia.Ephyra. The visible name is Home Cinema.
tags: [decision, name]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Status

Accepted (2026-11-03) by the owner, who created `nexumia-de/Ephyra` and renamed it to `nexumia-de/ephyra` on 2026-11-04.
The visible name **Home Cinema** was chosen by the owner on 2026-11-06
(issue #25), from the suggestions Media Stream, Home Cinema, Media and
Ephyra, under the toolkit decision
[code names and visible names](../../../phosh-toolkit/docs/decisions/app-names.md).

# Decision

*Ephyra* is the free-swimming young stage of a jellyfish: a nod to
Jellyfin without using its name or logo, short and unique. App id
`de.nexumia.Ephyra`, Python package and command `ephyra`, repository
`nexumia-de/ephyra`.

Users see **Home Cinema**: the `.desktop` `Name`, the metainfo `<name>`,
the window title, the About dialog and the welcome page; the nightly
build says "Home Cinema (Nightly)". `GenericName` is "Media Player" and
the keywords include `ephyra` and `jellyfin`, so search finds the app by
either name. The Jellyfin client name (`MediaBrowser Client="Ephyra"`),
the device profile, the keyring labels and the `User-Agent` keep the
code name.

# Consequences

Names with "Jelly…" were avoided so the app is not mistaken for an
official Jellyfin client. Whether the name is free on Flathub was not
checked (Flathub blocked in the cloud environment). On 2026-11-06
Flathub's search had no app named "Home Cinema"; "Cinema" is taken
(`com.github.artemanufrij.playmyvideos`).
