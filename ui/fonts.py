"""
ui/fonts.py — Application font loader.

Registers bundled TTF/OTF files from assets/fonts/ at startup so the rest
of the UI can reference them by family name via QFont / stylesheets.

Usage (call once, before any widgets are created):
    from ui.fonts import load_app_fonts, FONT_FAMILY_UI
    load_app_fonts()

Bundled font committed to assets/fonts/:
  Nunito-VF.ttf  — Nunito variable font (wght 200–900, SIL OFL 1.1)
  Source: https://github.com/googlefonts/nunito

Fallback chain when file is missing:
  "Segoe UI Variable" (Win 11 variable font) → "Segoe UI" → sans-serif
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QFontDatabase

# ── Public constants — import these everywhere instead of hard-coding strings ─
FONT_FAMILY_UI     = "Nunito"          # primary — warmth + legibility
FONT_FAMILY_SYSTEM = "Segoe UI Variable, Segoe UI"  # plain system fallback


def _fonts_dir() -> Path:
    """Return the assets/fonts directory, resolved from this file's location."""
    return Path(__file__).resolve().parent.parent / "assets" / "fonts"


def load_app_fonts() -> bool:
    """Register bundled fonts.  Returns True if Nunito was loaded successfully."""
    fonts_dir = _fonts_dir()
    loaded = False

    if fonts_dir.is_dir():
        for ttf in sorted(fonts_dir.glob("*.ttf")) + sorted(fonts_dir.glob("*.otf")):
            fid = QFontDatabase.addApplicationFont(str(ttf))
            if fid != -1:
                loaded = True

    return loaded
