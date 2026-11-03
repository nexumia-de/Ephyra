"""Item images: fetched through the connection, cached on disk and as
textures in memory."""
import logging
from collections import OrderedDict

from gi.repository import Gdk, GLib

from ephyra import settings

log = logging.getLogger("ephyra.images")

MEMORY = 300


class Images:
    def __init__(self, connection):
        self.connection = connection
        self._cache = OrderedDict()
        self._waiting = {}
        self._dir = settings.cache_dir() / "images"

    def load(self, item_id, kind, tag, width, done):
        """done(texture or None) on the main loop. `width` in logical
        pixels; the server scales to twice that for HiDPI screens."""
        key = (item_id, kind, tag or "", width)
        if key in self._cache:
            self._cache.move_to_end(key)
            done(self._cache[key])
            return
        if key in self._waiting:
            self._waiting[key].append(done)
            return
        self._waiting[key] = [done]
        path = self._dir / f"{item_id}-{kind}-{tag or 'none'}-{width}.jpg"

        def fetch():
            try:
                data = path.read_bytes()
            except OSError:
                data = self.connection.jellyfin.image(item_id, kind, tag,
                                                      width * 2)
                try:
                    self._dir.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                except OSError as e:
                    log.info("image cache: %s", e)
            return Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))

        def finished(texture, error):
            if error is not None:
                log.debug("image %s %s: %s", item_id, kind, error)
                texture = None
            else:
                self._cache[key] = texture
                while len(self._cache) > MEMORY:
                    self._cache.popitem(last=False)
            for callback in self._waiting.pop(key, []):
                callback(texture)

        self.connection.call(fetch, finished)


def primary(item):
    """(item id, kind, tag) of the image a card shows: the item's own
    poster, else its series' or album's."""
    tags = item.get("ImageTags") or {}
    if tags.get("Primary"):
        return item["Id"], "Primary", tags["Primary"]
    if item.get("SeriesPrimaryImageTag"):
        return item["SeriesId"], "Primary", item["SeriesPrimaryImageTag"]
    if item.get("AlbumPrimaryImageTag"):
        return item["AlbumId"], "Primary", item["AlbumPrimaryImageTag"]
    return None


def landscape(item):
    """A 16:9 image for "Continue Watching": the episode's own still, a
    thumb or the backdrop."""
    tags = item.get("ImageTags") or {}
    if item.get("Type") == "Episode" and tags.get("Primary"):
        return item["Id"], "Primary", tags["Primary"]
    if tags.get("Thumb"):
        return item["Id"], "Thumb", tags["Thumb"]
    if item.get("BackdropImageTags"):
        return item["Id"], "Backdrop", item["BackdropImageTags"][0]
    if item.get("ParentBackdropImageTags"):
        return (item.get("ParentBackdropItemId"), "Backdrop",
                item["ParentBackdropImageTags"][0])
    return primary(item)


def backdrop(item):
    if item.get("BackdropImageTags"):
        return item["Id"], "Backdrop", item["BackdropImageTags"][0]
    if item.get("ParentBackdropImageTags"):
        return (item.get("ParentBackdropItemId"), "Backdrop",
                item["ParentBackdropImageTags"][0])
    return None
