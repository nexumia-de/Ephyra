"""The Jellyfin REST API (server 10.9 or newer), blocking calls meant for
worker threads; see ephyra/tasks.py for running them from the UI.
No GTK."""
import json
import socket
from urllib.parse import quote, urlencode

from ephyra import CLIENT_NAME, VERSION
from ephyra.http import Client, HttpError, SERVER  # noqa: F401

TICKS_PER_SECOND = 10_000_000
# Item fields the views need besides the defaults.
FIELDS = "Overview,PrimaryImageAspectRatio,Genres,ProductionYear,ChildCount"


def _quote(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


class Jellyfin:
    def __init__(self, http=None, device_id="", device_name=None):
        self.http = http or Client()
        self.device_id = device_id
        self.device_name = device_name or socket.gethostname() or "Phosh"
        self.base_url = ""      # set by Connection for the current route
        self.token = ""
        self.user_id = ""

    # --- plumbing -----------------------------------------------------

    def authorization(self):
        parts = [f'Client="{CLIENT_NAME}"',
                 f'Device="{_quote(self.device_name)}"',
                 f'DeviceId="{_quote(self.device_id)}"',
                 f'Version="{VERSION}"']
        if self.token:
            parts.append(f'Token="{_quote(self.token)}"')
        return "MediaBrowser " + ", ".join(parts)

    def url(self, path, base=None, **query):
        query = {k: v for k, v in query.items() if v is not None and v != ""}
        for k, v in query.items():
            if isinstance(v, bool):
                query[k] = "true" if v else "false"
        url = (base or self.base_url) + path
        return url + ("?" + urlencode(query) if query else "")

    def get(self, path, base=None, timeout=None, **query):
        response = self.http.request(
            "GET", self.url(path, base, **query),
            {"Authorization": self.authorization(),
             "Accept": "application/json"}, timeout=timeout)
        return _json(response.body)

    def post(self, path, payload=None, **query):
        body = json.dumps(payload).encode() if payload is not None else b""
        response = self.http.request(
            "POST", self.url(path, **query),
            {"Authorization": self.authorization(),
             "Accept": "application/json"}, body=body)
        return _json(response.body)

    def delete(self, path, **query):
        response = self.http.request(
            "DELETE", self.url(path, **query),
            {"Authorization": self.authorization(),
             "Accept": "application/json"})
        return _json(response.body)

    # --- server and account ---------------------------------------------

    def public_info(self, base, timeout=None):
        """{Id, ServerName, Version, …}; needs no token."""
        info = self.get("/System/Info/Public", base=base, timeout=timeout)
        if not isinstance(info, dict) or not info.get("Id"):
            raise HttpError(SERVER, "This is not a Jellyfin server")
        return info

    def authenticate(self, user, password):
        result = self.post("/Users/AuthenticateByName",
                           {"Username": user, "Pw": password})
        self.token = result["AccessToken"]
        self.user_id = result["User"]["Id"]
        return result

    def sign_out(self):
        self.post("/Sessions/Logout")

    # --- browsing --------------------------------------------------------

    def views(self):
        return self.get("/UserViews", userId=self.user_id)["Items"]

    def resume(self, limit=12):
        return self.get("/UserItems/Resume", userId=self.user_id,
                        limit=limit, mediaTypes="Video", fields=FIELDS,
                        enableImageTypes="Primary,Backdrop,Thumb")["Items"]

    def next_up(self, limit=12, series_id=None):
        return self.get("/Shows/NextUp", userId=self.user_id, limit=limit,
                        seriesId=series_id, fields=FIELDS,
                        enableResumable=False)["Items"]

    def latest(self, parent_id, limit=12):
        return self.get("/Items/Latest", userId=self.user_id,
                        parentId=parent_id, limit=limit, fields=FIELDS)

    def items(self, parent_id=None, start=0, limit=60, types=None,
              recursive=False, search=None, sort="SortName",
              order="Ascending"):
        """{Items, TotalRecordCount}"""
        return self.get("/Items", userId=self.user_id, parentId=parent_id,
                        startIndex=start, limit=limit,
                        includeItemTypes=types, recursive=recursive,
                        searchTerm=search, sortBy=sort, sortOrder=order,
                        fields=FIELDS, imageTypeLimit=1,
                        enableImageTypes="Primary,Backdrop,Thumb")

    def item(self, item_id):
        return self.get(f"/Items/{quote(item_id)}", userId=self.user_id)

    def seasons(self, series_id):
        return self.get(f"/Shows/{quote(series_id)}/Seasons",
                        userId=self.user_id, fields=FIELDS)["Items"]

    def episodes(self, series_id, season_id):
        return self.get(f"/Shows/{quote(series_id)}/Episodes",
                        userId=self.user_id, seasonId=season_id,
                        fields=FIELDS)["Items"]

    def set_played(self, item_id, played):
        path = f"/UserPlayedItems/{quote(item_id)}"
        if played:
            return self.post(path, userId=self.user_id)
        return self.delete(path, userId=self.user_id)

    def set_favorite(self, item_id, favorite):
        path = f"/UserFavoriteItems/{quote(item_id)}"
        if favorite:
            return self.post(path, userId=self.user_id)
        return self.delete(path, userId=self.user_id)

    def image(self, item_id, kind="Primary", tag=None, width=None):
        """JPEG bytes of an item image, scaled by the server."""
        url = self.url(f"/Items/{quote(item_id)}/Images/{kind}",
                       tag=tag, maxWidth=width, quality=90)
        return self.http.request("GET", url, {
            "Authorization": self.authorization()}).body

    # --- playback (docs/playback.md) ---------------------------------------

    def playback_info(self, item_id, max_bitrate, start_ticks=0,
                      audio_index=None, force_transcode=False):
        """force_transcode: the phone failed to play the original, let the
        server convert it."""
        from ephyra.playback import device_profile
        return self.post(
            f"/Items/{quote(item_id)}/PlaybackInfo",
            {"UserId": self.user_id,
             "MaxStreamingBitrate": max_bitrate or 140_000_000,
             "StartTimeTicks": start_ticks,
             "AudioStreamIndex": audio_index,
             # No subtitle rendering yet: never burn them in.
             "SubtitleStreamIndex": -1,
             "EnableDirectPlay": not force_transcode,
             "EnableDirectStream": not force_transcode,
             "EnableTranscoding": True,
             "AutoOpenLiveStream": True,
             "DeviceProfile": device_profile(max_bitrate)})

    def report(self, event, payload):
        """event: "" (started), "Progress" or "Stopped"."""
        path = "/Sessions/Playing" + (f"/{event}" if event else "")
        self.post(path, payload)


def _json(body):
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        raise HttpError(SERVER, "The server sent an invalid answer") from None
