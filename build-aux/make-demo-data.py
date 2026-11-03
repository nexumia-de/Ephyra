"""Writes the demo library in tests/data/demo/: library.json and the poster,
backdrop and thumbnail images, drawn here (own work, CC0-1.0, JPEG). Titles are
invented. Run once after changing it:

    /usr/bin/python3 build-aux/make-demo-data.py

Needs pycairo and GdkPixbuf (python3-cairo, gir1.2-gdkpixbuf-2.0)."""
import hashlib
import json
import math
from pathlib import Path

import cairo
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "data" / "demo"

# (hue pair) per title; drawn as a gradient with simple shapes.
PALETTES = [
    ((0.05, 0.18, 0.32), (0.00, 0.55, 0.75)),
    ((0.30, 0.10, 0.35), (0.85, 0.40, 0.55)),
    ((0.10, 0.25, 0.15), (0.55, 0.75, 0.35)),
    ((0.35, 0.18, 0.05), (0.95, 0.65, 0.25)),
    ((0.08, 0.08, 0.20), (0.40, 0.45, 0.85)),
    ((0.25, 0.05, 0.05), (0.85, 0.25, 0.20)),
    ((0.05, 0.22, 0.25), (0.30, 0.80, 0.75)),
    ((0.20, 0.20, 0.22), (0.70, 0.70, 0.75)),
]


def uid(name):
    return hashlib.md5(name.encode()).hexdigest()


def draw(path, w, h, title, palette, seed):
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    cr = cairo.Context(surface)
    top, bottom = palette
    grad = cairo.LinearGradient(0, 0, w * 0.3, h)
    grad.add_color_stop_rgb(0, *top)
    grad.add_color_stop_rgb(1, *bottom)
    cr.set_source(grad)
    cr.paint()
    # A few soft circles, placed from the seed.
    for i in range(5):
        x = (seed * (i + 3) * 37 % 100) / 100 * w
        y = (seed * (i + 7) * 53 % 100) / 100 * h
        r = (0.15 + (seed * (i + 1) % 30) / 100) * min(w, h)
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.set_source_rgba(1, 1, 1, 0.06 + 0.02 * i)
        cr.fill()
    if title:
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD)
        size = w / 9
        cr.set_font_size(size)
        words, lines, line = title.split(), [], ""
        for word in words:
            test = (line + " " + word).strip()
            if cr.text_extents(test).width > w * 0.84 and line:
                lines.append(line)
                line = word
            else:
                line = test
        lines.append(line)
        y = h * 0.78 - (len(lines) - 1) * size * 1.15
        for text in lines:
            ext = cr.text_extents(text)
            cr.move_to((w - ext.width) / 2 - ext.x_bearing, y)
            cr.set_source_rgba(1, 1, 1, 0.92)
            cr.show_text(text)
            y += size * 1.15
    # JPEG like a real server sends, and much smaller than PNG.
    tmp = path.with_suffix(".png")
    surface.write_to_png(str(tmp))
    GdkPixbuf.Pixbuf.new_from_file(str(tmp)).savev(
        str(path), "jpeg", ["quality"], ["82"])
    tmp.unlink()


def main():
    images = OUT / "images"
    images.mkdir(parents=True, exist_ok=True)
    items = []
    n = 0

    def image(item, kind, w, h, title):
        nonlocal n
        n += 1
        draw(images / f"{item['Id']}-{kind}.jpg", w, h, title,
             PALETTES[n % len(PALETTES)], n * 7 + 3)
        tag = uid(item["Id"] + kind)[:8]
        if kind == "Backdrop":
            item["BackdropImageTags"] = [tag]
        else:
            item.setdefault("ImageTags", {})[kind] = tag

    def add(**fields):
        item = {"Id": uid(fields["Name"] + fields.get("ParentId", "")),
                "ServerId": SERVER_ID, "UserData": {"Played": False,
                                                    "PlaybackPositionTicks": 0,
                                                    "IsFavorite": False}}
        item.update(fields)
        items.append(item)
        return item

    views = {}
    for name, ctype in (("Movies", "movies"), ("Shows", "tvshows"),
                        ("Music", "music")):
        views[ctype] = add(Name=name, Type="CollectionFolder",
                           CollectionType=ctype, IsFolder=True)
        image(views[ctype], "Primary", 480, 270, name)

    movies = [
        ("The Lighthouse Keeper", 2021, 6720, "A keeper on a remote island "
         "finds letters that someone keeps leaving at his door."),
        ("Northern Lights", 2019, 5880, "Two sisters drive across Finland "
         "in winter to scatter their father's ashes."),
        ("Paper Boats", 2023, 5400, "A summer in a small harbour town, "
         "told by the children who build boats from old newspapers."),
        ("Salt and Iron", 2018, 7260, "The last foundry of a mining town "
         "gets one more order."),
        ("A Quiet Orbit", 2024, 6300, "An astronaut alone on a station "
         "talks to the ground crew for 90 days."),
        ("Glass Garden", 2020, 6060, "A botanist restores a ruined "
         "greenhouse and the town that forgot it."),
        ("Moth Season", 2022, 5640, "Late-night radio, insomnia and a "
         "caller who knows too much."),
        ("Under the Pier", 2017, 5100, "A comedy about a lifeguard who "
         "can't swim."),
    ]
    for i, (name, year, minutes, overview) in enumerate(movies):
        movie = add(Name=name, Type="Movie", MediaType="Video",
                    ParentId=views["movies"]["Id"], ProductionYear=year,
                    RunTimeTicks=minutes * 10_000_000, Overview=overview,
                    OfficialRating="12", CommunityRating=round(6.1 + i * 0.3, 1),
                    Genres=["Drama"], PrimaryImageAspectRatio=0.6667)
        image(movie, "Primary", 400, 600, name)
        image(movie, "Backdrop", 960, 540, "")
    lighthouse = items[3]
    lighthouse["UserData"]["PlaybackPositionTicks"] = 2400 * 10_000_000
    lighthouse["UserData"]["PlayedPercentage"] = 35.7
    items[5]["UserData"]["Played"] = True

    series_ids = []
    for s, (name, year, overview, seasons) in enumerate((
            ("Harbour Tales", 2022, "Every episode follows one boat that "
             "comes into the harbour of Kesterby.", (6, 4)),
            ("Night Market", 2024, "Food, stories and trouble at a market "
             "that opens at midnight.", (8,)))):
        series = add(Name=name, Type="Series", IsFolder=True,
                     ParentId=views["tvshows"]["Id"], ProductionYear=year,
                     Overview=overview, ChildCount=len(seasons),
                     PrimaryImageAspectRatio=0.6667)
        image(series, "Primary", 400, 600, name)
        image(series, "Backdrop", 960, 540, "")
        series_ids.append(series["Id"])
        for number, count in enumerate(seasons, start=1):
            season = add(Name=f"Season {number}", Type="Season",
                         IsFolder=True, ParentId=series["Id"],
                         SeriesId=series["Id"], SeriesName=name,
                         IndexNumber=number, ChildCount=count)
            image(season, "Primary", 400, 600, f"{name} {number}")
            for e in range(1, count + 1):
                episode = add(
                    Name=f"Episode {e}", Type="Episode", MediaType="Video",
                    ParentId=season["Id"], SeasonId=season["Id"],
                    SeriesId=series["Id"], SeriesName=name,
                    ParentIndexNumber=number, IndexNumber=e,
                    RunTimeTicks=(42 + e) * 60 * 10_000_000,
                    Overview=f"Part {e} of season {number} of {name}.")
                image(episode, "Primary", 480, 270, "")
                if s == 0 and number == 1 and e <= 3:
                    episode["UserData"]["Played"] = True
    album = add(Name="Tidal Sketches", Type="MusicAlbum", IsFolder=True,
                ParentId=views["music"]["Id"], ProductionYear=2020,
                AlbumArtist="The Low Tides", ChildCount=4)
    image(album, "Primary", 500, 500, "Tidal Sketches")
    for t, title in enumerate(("Ebb", "Driftwood", "Slack Water", "Flood"), 1):
        add(Name=title, Type="Audio", MediaType="Audio",
            ParentId=album["Id"], AlbumId=album["Id"], Album=album["Name"],
            AlbumArtist="The Low Tides", IndexNumber=t,
            RunTimeTicks=(180 + t * 20) * 10_000_000)

    harbour_ep4 = next(i for i in items if i.get("SeriesName") == "Harbour Tales"
                       and i.get("ParentIndexNumber") == 1 and i.get("IndexNumber") == 4)
    library = {
        "server": {"Id": SERVER_ID, "ServerName": "Home Media",
                   "Version": "10.11.0", "ProductName": "Jellyfin Server",
                   "StartupWizardCompleted": True},
        "user": {"Id": uid("demo user"), "Name": "Robin"},
        "resume": [lighthouse["Id"]],
        "next_up": [harbour_ep4["Id"]],
        "items": items,
    }
    (OUT / "library.json").write_text(json.dumps(library, indent=1) + "\n")
    print(len(items), "items,", n, "images")


SERVER_ID = uid("demo server")

if __name__ == "__main__":
    main()
