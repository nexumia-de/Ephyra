---
type: Playbook
title: Development environment
description: Hosts the cloud environment needs, host packages, and how to run, test, screenshot and build Ephyra.
tags: [development, environment, hosts, testing]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Hosts

Unreachable from the cloud environment on 2026-11-03 (proxy `403`):

| Host | Needed for |
|---|---|
| `dl.flathub.org` | GNOME runtime and SDK for a local Flatpak build (CI builds it otherwise) |
| `api.jellyfin.org`, `jellyfin.org`, `repo.jellyfin.org` | Jellyfin API reference and docs |
| `developer.gnome.org`, `gnome.pages.gitlab.gnome.org` | GNOME HIG and libadwaita docs |

Workaround used: the Jellyfin sources are cloned with git
(`github.com/jellyfin/jellyfin`, `jellyfin-web`), which works.

# Host packages (Ubuntu 24.04)

After `bash ../phosh-toolkit/setup.sh`:

```sh
sudo apt-get install gir1.2-soup-3.0 gir1.2-secret-1 gir1.2-gstreamer-1.0 \
  gstreamer1.0-plugins-good gstreamer1.0-libav python3-pytest python3-cairo xvfb
```

The cloud image's default `python3` (3.13) has no `gi`; use
`/usr/bin/python3.12`.

# Run, test, screenshot

```sh
export PYTHONPATH=$PWD/../phosh-toolkit/lib                     # shared package
EPHYRA_DEMO=$PWD/tests/data/demo /usr/bin/python3.12 -m ephyra   # demo library
/usr/bin/python3.12 -m ephyra                                    # real server
dbus-run-session -- xvfb-run -a /usr/bin/python3.12 -m pytest   # all tests, as in CI
../phosh-toolkit/scripts/screenshot.sh -e EPHYRA_DEMO=$PWD/tests/data/demo -e PYTHONPATH=$PYTHONPATH -o shot.png -- /usr/bin/python3.12 -m ephyra
```

The tests find the shared package in the sibling checkout
`../phosh-toolkit` by themselves; CI checks out phosh-toolkit at the
commit the manifest pins (`tests.yml`).

`EPHYRA_DEBUG=1` logs the route, proxy requests and playback.
`EPHYRA_KEYRING=memory` keeps secrets in memory (tests, screenshots).
CI has a session bus, so the UI tests share one application (a second
one with the same id can't register); run them under `dbus-run-session`
to match. The tests make their own CA and certificates with `openssl` and run the
demo server behind mutual TLS.
Tests that play media own GLib's default context while they do, as
the app's main loop does: the `main_context` fixture for whole tests,
`owning_main_context()` around the player parts of the UI test. Without
it gtk4paintablesink sometimes aborts ("Value accessed from different
thread than where it was created"), about one run in three.

Host screenshots use libadwaita 1.5: the CSS variables in `style.css`
print parser warnings and `.dimmed` has no effect; the `@define-color`
fallback keeps the accent.
