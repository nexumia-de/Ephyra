# Ephyra

Named after the *ephyra*, the young stage of a jellyfish.

Adaptive GTK4/libadwaita client for [Jellyfin](https://jellyfin.org/)
media servers on [Phosh](https://phosh.mobi/) phones and the desktop,
in the look of Jellyfin's own apps: continue watching, next episodes,
libraries, search, details, and a touch player that resumes where you
stopped.

- **Home and away**: on your home Wi-Fi Ephyra talks to the server's
  local address; everywhere else it uses the public one.
- **Client certificates**: servers behind mutual TLS work with a
  PKCS #12 (`.p12`) or PEM certificate.
- **Phone-friendly streaming**: separate quality limits at home and
  away; the server converts what the phone can't play.

Status: first version (milestone M0), not yet tested on a phone. See
the [milestones](https://github.com/nexumia-de/ephyra/milestones) and
[docs/roadmap.md](docs/roadmap.md). Needs Jellyfin 10.9 or newer.

Ephyra is an independent project and not affiliated with the Jellyfin
project.

## Install

After the first release, on the phone open <https://flatpak.nexumia.de/>
and tap Ephyra; GNOME Software installs it and keeps it updated.
*Ephyra (Nightly)* follows every push to `main`. See
[docs/release-channels.md](docs/release-channels.md).

## Support

Ephyra is free for everyone. If you want to support its development
and more free apps, you can do so on
[Liberapay](https://liberapay.com/suitably). What the money pays for
and which fees each platform takes:
[support](https://github.com/nexumia-de/phosh-toolkit/blob/main/docs/support.md).

## Development

This repository uses
[phosh-toolkit](https://github.com/nexumia-de/phosh-toolkit), checked out
next to it:

```
workspace/
  phosh-toolkit/
  ephyra/
```

```sh
[ -d phosh-toolkit ] || git clone https://github.com/nexumia-de/phosh-toolkit.git
bash phosh-toolkit/setup.sh
```

Run with `python3 -m ephyra` (or with the demo library:
`EPHYRA_DEMO=$PWD/tests/data/demo python3 -m ephyra`), test with
`xvfb-run -a python3 -m pytest` with phosh-toolkit checked out next to this repository. Details:
[docs/dev-environment.md](docs/dev-environment.md).

Agent rules: [AGENTS.md](AGENTS.md). Knowledge bundle:
[docs/index.md](docs/index.md).

## License

GNU Affero General Public License v3.0 or later
(`AGPL-3.0-or-later`), see [LICENSE](LICENSE). Why:
[license decision](docs/decisions/license.md). Contributions are
accepted only under the terms in [CONTRIBUTING.md](CONTRIBUTING.md).
