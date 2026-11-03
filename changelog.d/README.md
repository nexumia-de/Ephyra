# Changelog fragments

Every pull request that changes something users notice adds one file
here: `<slug>.<type>.md` with one sentence for users, in English, e.g.
`continue-watching.feature.md`. Types: `feature` (new), `improvement`
(better), `fix` (repaired). Blank lines separate several entries in one
file.

The release pull request collects them into the `<release>` of
`data/de.nexumia.Ephyra.metainfo.xml`, which GNOME Software, the About
dialog and the GitHub release show, and deletes them. Changes that
users do not notice (docs, tests, CI) need no fragment; the pull request
then gets the label `no-changelog` if the check asks for one. Details:
`docs/release-channels.md`.
