"""
paths.py — Resolve filesystem paths correctly whether running from source
or from a frozen PyInstaller bundle.

When frozen by PyInstaller, there are two distinct anchor points:

* ``sys._MEIPASS`` — directory containing bundled (read-only) datas.
  In one-folder mode this is the ``_internal/`` folder next to the exe.
* ``Path(sys.executable).parent`` — the install folder itself. The user's
  writable ``config.yaml`` lives here so it survives reinstall and is easy
  for users to find and edit.

In source mode both anchors collapse to the project root.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _resolve_install_dir() -> Path:
    """Directory holding the executable (or project root in source mode)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
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

