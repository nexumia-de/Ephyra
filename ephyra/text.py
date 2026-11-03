"""Labels for items and times, as Jellyfin's apps word them. No GTK."""
TICKS = 10_000_000


def duration(ticks):
    """"1 h 52 min", "45 min", "3:20" for audio-length items."""
    seconds = int((ticks or 0) / TICKS)
    if seconds <= 0:
        return ""
    if seconds < 600:
        return clock(seconds)
    hours, minutes = divmod(round(seconds / 60), 60)
    if hours:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    return f"{minutes} min"


def clock(seconds):
    """"1:02:03" or "2:03"."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def episode_code(item):
    """"S1:E4" like Jellyfin, or ""."""
    season, number = item.get("ParentIndexNumber"), item.get("IndexNumber")
    if season is None or number is None:
        return ""
    return f"S{season}:E{number}"


def subtitle(item):
    """Second line under a poster."""
    kind = item.get("Type")
    if kind == "Episode":
        code = episode_code(item)
        return f"{code} · {item['Name']}" if code else item.get("Name", "")
    if kind == "Season":
        count = item.get("ChildCount")
        return f"{count} episodes" if count else ""
    if kind == "MusicAlbum":
        return item.get("AlbumArtist") or str(item.get("ProductionYear") or "")
    if kind == "CollectionFolder":
        return ""
    year = item.get("ProductionYear")
    return str(year) if year else ""


def title(item):
    """First line under a poster: episodes are named by their series."""
    if item.get("Type") == "Episode" and item.get("SeriesName"):
        return item["SeriesName"]
    return item.get("Name", "")


def facts(item):
    """"2021 · 1 h 52 min · 12 · ★ 7.1" for the detail page."""
    parts = []
    if item.get("Type") == "Episode" and episode_code(item):
        parts.append(episode_code(item))
    if item.get("ProductionYear"):
        parts.append(str(item["ProductionYear"]))
    if item.get("Type") == "Series" and item.get("ChildCount"):
        n = item["ChildCount"]
        parts.append(f"{n} season" + ("" if n == 1 else "s"))
    if duration(item.get("RunTimeTicks")):
        parts.append(duration(item["RunTimeTicks"]))
    if item.get("OfficialRating"):
        parts.append(item["OfficialRating"])
    if item.get("CommunityRating"):
        parts.append(f"★ {item['CommunityRating']:.1f}")
    return " · ".join(parts)


def resume_seconds(item):
    data = item.get("UserData") or {}
    if data.get("Played"):
        return 0
    return (data.get("PlaybackPositionTicks") or 0) / TICKS


def played_fraction(item):
    data = item.get("UserData") or {}
    if data.get("PlayedPercentage"):
        return data["PlayedPercentage"] / 100
    total = item.get("RunTimeTicks") or 0
    if total and data.get("PlaybackPositionTicks"):
        return data["PlaybackPositionTicks"] / total
    return 0


def ends_at(item, now, position=0):
    """"Ends at 22:14" for the remaining run time from `now`
    (a datetime)."""
    from datetime import timedelta
    total = (item.get("RunTimeTicks") or 0) / TICKS
    if total <= 0:
        return ""
    end = now + timedelta(seconds=total - position)
    return f"Ends at {end:%H:%M}"
