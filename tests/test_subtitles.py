"""SRT cues for the subtitles Ephyra draws (ephyra/subtitles.py)."""
from ephyra.subtitles import Track, markup, parse_srt

SRT = """﻿1
00:00:01,000 --> 00:00:03,500
<i>Hello</i> & <font color="red">welcome</font>

2
00:00:03,000 --> 00:00:05,000
{\\an8}Second line
over two rows

3
00:01:02.5 --> 00:01:04,000
Late
"""


def test_parse_and_lookup():
    cues = parse_srt(SRT.lstrip("﻿"))
    assert [(c[0], c[1]) for c in cues] == [(1, 3.5), (3, 5), (62.5, 64)]
    track = Track(cues)
    assert track.at(0.5) == ""
    assert track.at(1) == "<i>Hello</i> &amp; welcome"
    # Overlapping cues show together.
    assert track.at(3.2) == "<i>Hello</i> &amp; welcome\nSecond line\nover two rows"
    assert track.at(63) == "Late"
    assert track.at(64) == ""


def test_markup_keeps_simple_tags_only():
    assert markup("<b>bold</b> <u>u</u> <x>") == "<b>bold</b> <u>u</u>"
    # Unbalanced tags are dropped instead of breaking the markup.
    assert markup("<i>open only") == "open only"
    assert markup("a < b") == "a &lt; b"
