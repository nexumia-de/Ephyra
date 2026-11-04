# Decision records

* [App name Ephyra](app-name.md) - Named after the young stage of a jellyfish; app id de.nexumia.Ephyra.
* [AGPL-3.0 license](license.md) - Like Cirro; no Jellyfin code copied in.
* [Python and PyGObject](python-pygobject.md) - Same stack as Cirro, everything from the GNOME runtime.
* [Jellyfin look](jellyfin-style.md) - Jellyfin's style instead of the toolkit's stock look, at the owner's request.
* [Local media proxy](media-proxy.md) - GStreamer plays a 127.0.0.1 URL; the proxy adds token and client certificate.
* [playbin instead of GtkMediaFile](playbin.md) - GTK 4.20's media file reads http:// through GIO, which the Flatpak can't; playbin3 with gtk4paintablesink plays the proxy URL.
