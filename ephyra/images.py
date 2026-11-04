"""Item images: fetched through the connection, cached on disk and as
textures in memory (phosh_toolkit.images)."""
from phosh_toolkit.images import ImageCache

from ephyra import settings


class Images:
    def __init__(self, connection):
        self.connection = connection
        self._cache = ImageCache(settings.cache_dir() / "images", connection.call)

    def load(self, item_id, kind, tag, width, done):
        """done(texture or None) on the main loop. `width` in logical
        pixels; the server scales to twice that for HiDPI screens."""
        name = f"{item_id}-{kind}-{tag or 'none'}-{width}.jpg"
        self._cache.load(name, lambda: self.connection.jellyfin.image(
            item_id, kind, tag, width * 2), done)


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
