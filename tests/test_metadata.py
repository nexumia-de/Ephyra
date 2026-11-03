import re
import xml.etree.ElementTree as ET
from pathlib import Path

import ephyra

ROOT = Path(__file__).resolve().parent.parent
APP_ID = "de.nexumia.Ephyra"


def test_version_matches_meson_and_metainfo():
    meson = (ROOT / "meson.build").read_text()
    assert re.search(r"version: '([^']+)'", meson).group(1) == ephyra.VERSION
    metainfo = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml")
    assert metainfo.find("releases/release").get("version") == ephyra.VERSION


def test_every_module_is_installed():
    meson = (ROOT / "meson.build").read_text()
    for path in (ROOT / "ephyra").glob("*.py"):
        assert f"'ephyra/{path.name}'" in meson, path.name


def test_desktop_file_is_shown_in_phosh_mobile_mode():
    desktop = (ROOT / "data" / f"{APP_ID}.desktop").read_text()
    # Phosh matches the substring "mobile;" case-insensitively.
    assert re.search(r"^X-Purism-FormFactor=.*mobile;", desktop,
                     re.IGNORECASE | re.MULTILINE)


def test_metainfo_declares_phone_support():
    root = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml").getroot()
    length = root.find("recommends/display_length")
    assert length.get("compare") == "ge" and length.text == "360"
    controls = {c.text for c in root.findall("supports/control")}
    assert {"touch", "pointing", "keyboard"} <= controls


def test_metainfo_donation_url_matches_about_dialog():
    root = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml").getroot()
    assert root.find("url[@type='donation']").text == ephyra.SUPPORT_URL


def test_flatpak_may_read_the_wifi_name():
    manifest = (ROOT / f"{APP_ID}.yml").read_text()
    assert "--system-talk-name=org.freedesktop.NetworkManager" in manifest


def test_stable_build_from_source_tree():
    assert ephyra.APP_ID == APP_ID and not ephyra.NIGHTLY
    assert ephyra.VERSION_LABEL == ephyra.VERSION
