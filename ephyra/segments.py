"""Media segments (intro, recap, credits …) from Jellyfin 10.10's
`GET /MediaSegments/{itemId}`, and when the player offers to skip one or
to go on to the next episode (docs/player-controls.md). No GTK."""
from collections import namedtuple

TICKS = 10_000_000
# Jellyfin's MediaSegmentType names and the button that skips them.
SKIP_LABELS = {
    "Intro": "Skip Intro",
    "Recap": "Skip Recap",
    "Preview": "Skip Preview",
    "Commercial": "Skip Ad",
    "Outro": "Skip Credits",
}
UP_NEXT_BEFORE = 30   # seconds before the end, when there are no credits marked
SHORTEST = 1          # seconds; shorter segments are not offered

Segment = namedtuple("Segment", "kind start end")


def parse(answer):
    """Segments from the server's answer ({Items: [...]}), sorted by start;
    unknown types and segments too short to skip are left out."""
    out = []
    for raw in (answer or {}).get("Items") or []:
        kind = raw.get("Type")
        start = (raw.get("StartTicks") or 0) / TICKS
        end = (raw.get("EndTicks") or 0) / TICKS
        if kind in SKIP_LABELS and end - start >= SHORTEST:
            out.append(Segment(kind, start, end))
    return sorted(out, key=lambda s: s.start)


def at(segments, position):
    """The segment playing at `position` (seconds), or None. The last
    second of a segment no longer counts: skipping it would gain nothing."""
    for segment in segments:
        if segment.start <= position < segment.end - SHORTEST:
            return segment
    return None


def up_next_from(segments, duration):
    """When the next episode is offered: at the start of the credits that
    run to the end (an `Outro` in the last quarter), else 30 s before the
    end. None without a known duration."""
    if not duration or duration <= 0:
        return None
    for segment in reversed(segments):
        if segment.kind == "Outro" and segment.start >= duration * 0.75:
            return segment.start
    return max(0, duration - UP_NEXT_BEFORE)
