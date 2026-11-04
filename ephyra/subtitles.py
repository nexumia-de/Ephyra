"""Subtitles drawn by Ephyra over the video: the server sends the chosen
text subtitle as SRT, this module turns it into timed cues
(docs/playback.md, decision docs/decisions/subtitles-in-app.md)."""
import bisect
import re

from gi.repository import GLib

_TIME = re.compile(r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})")
_ARROW = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)")
_TAG = re.compile(r"<\s*(/?)\s*([biu])\s*>", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]*>|\{\\[^}]*\}")


def _seconds(stamp):
    match = _TIME.match(stamp)
    if not match:
        return None
    hours, minutes, seconds, millis = match.groups()
    return (int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            + int(millis.ljust(3, "0")) / 1000)


def markup(text):
    """SRT text as Pango markup: <b>, <i> and <u> stay, other tags (font,
    ASS overrides like {\\an8}) go."""
    parts = []
    position = 0
    for match in _TAG.finditer(text):
        parts.append(GLib.markup_escape_text(_ANY_TAG.sub("", text[position:match.start()])))
        parts.append(f"<{match.group(1)}{match.group(2).lower()}>")
        position = match.end()
    parts.append(GLib.markup_escape_text(_ANY_TAG.sub("", text[position:])))
    result = "".join(parts).strip()
    # Unbalanced tags would make the markup invalid: drop them then.
    for tag in "biu":
        if result.count(f"<{tag}>") != result.count(f"</{tag}>"):
            return GLib.markup_escape_text(_ANY_TAG.sub("", text).strip())
    return result


def parse_srt(text):
    """Cues (start, end, markup) in seconds, sorted by start."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        lines = block.strip("\n").split("\n")
        for i, line in enumerate(lines):
            match = _ARROW.match(line)
            if match:
                start, end = _seconds(match.group(1)), _seconds(match.group(2))
                body = "\n".join(lines[i + 1:]).strip()
                if start is not None and end is not None and body:
                    cues.append((start, end, markup(body)))
                break
    cues.sort(key=lambda cue: cue[0])
    return cues


class Track:
    """Cue lookup by position."""

    def __init__(self, cues):
        self.cues = cues
        self.starts = [cue[0] for cue in cues]

    def at(self, position):
        """Markup of the cues showing at `position` seconds, or ""."""
        end = bisect.bisect_right(self.starts, position)
        shown = [text for start, stop, text in self.cues[max(0, end - 8):end]
                 if start <= position < stop]
        return "\n".join(shown)
