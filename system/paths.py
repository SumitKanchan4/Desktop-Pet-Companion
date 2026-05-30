"""
paths.py — Resolve filesystem paths correctly whether running from source
or from a frozen PyInstaller bundle.

When frozen by PyInstaller, there are two distinct anchor points:

* ``sys._MEIPASS`` — directory containing bundled (read-only) datas.
  In one-folder mode this is the ``_internal/`` folder next to the exe.
* ``%APPDATA%\\Buddy`` — writable user-data directory for config.yaml.
  Using AppData means the app never needs write access to
  ``C:\\Program Files`` and config survives reinstall / updates.

In source mode both anchors collapse to the project root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _resolve_install_dir() -> Path:
    """Return the writable user-data directory.

    Frozen (installed to C:\\Program Files):  %APPDATA%\\Buddy
    Source mode:                               project root
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        data_dir = Path(appdata) / "Buddy"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    return Path(__file__).resolve().parent.parent


def _resolve_bundle_dir() -> Path:
    """Directory holding bundled read-only assets."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


# Writable / user-facing
APP_DIR: Path = _resolve_install_dir()
CONFIG_PATH: Path = APP_DIR / "config.yaml"

# Bundled / read-only
_BUNDLE_DIR: Path = _resolve_bundle_dir()
ASSETS_DIR: Path = _BUNDLE_DIR / "assets"
SPRITES_DIR: Path = ASSETS_DIR / "sprites"
CONFIG_EXAMPLE_PATH: Path = _BUNDLE_DIR / "config.example.yaml"
BARK_WAV_PATH: Path = ASSETS_DIR / "bark.wav"
TRAY_ICON_PATH: Path = ASSETS_DIR / "tray_icon.png"

