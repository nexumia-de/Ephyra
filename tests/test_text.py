from datetime import datetime

from ephyra import text


def test_duration():
    assert text.duration(6720 * 10_000_000) == "1 h 52 min"
    assert text.duration(3600 * 10_000_000) == "1 h"
    assert text.duration(2700 * 10_000_000) == "45 min"
    assert text.duration(200 * 10_000_000) == "3:20"
    assert text.duration(0) == ""


def test_clock():
    assert text.clock(5) == "0:05"
    assert text.clock(3723) == "1:02:03"


EPISODE = {"Type": "Episode", "Name": "Pilot", "SeriesName": "Harbour Tales",
           "ParentIndexNumber": 1, "IndexNumber": 4,
           "RunTimeTicks": 2700 * 10_000_000}


def test_episode_card():
    assert text.title(EPISODE) == "Harbour Tales"
    assert text.subtitle(EPISODE) == "S1:E4 · Pilot"
    assert text.facts(EPISODE) == "S1:E4 · 45 min"


def test_movie_facts():
    movie = {"Type": "Movie", "ProductionYear": 2021,
             "RunTimeTicks": 6720 * 10_000_000, "OfficialRating": "12",
             "CommunityRating": 7.14}
    assert text.facts(movie) == "2021 · 1 h 52 min · 12 · ★ 7.1"


def test_resume_and_ends_at():
    item = {"RunTimeTicks": 3600 * 10_000_000,
            "UserData": {"PlaybackPositionTicks": 1200 * 10_000_000}}
    assert text.resume_seconds(item) == 1200
    assert round(text.played_fraction(item), 2) == 0.33
    assert text.ends_at(item, datetime(2026, 11, 3, 20, 0), 1200) == "Ends at 20:40"
    item["UserData"]["Played"] = True
    assert text.resume_seconds(item) == 0
