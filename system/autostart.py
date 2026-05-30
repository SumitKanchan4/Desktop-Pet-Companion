"""
system/autostart.py — Windows registry helpers for run-on-login support.

Writes / removes a value under:
  HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

Using HKCU means no UAC prompt is required.  The key holds the full path
to the executable so it works from both source (python main.py) and a
frozen bundle (Buddy.exe).
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

_RUN_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "DesktopPetBuddy"


def _exe_command() -> str:
    """Return the command that should be stored in the registry."""
    if getattr(sys, "frozen", False):
        # Frozen bundle → just the exe path (no quotes needed for simple paths,
        # but we add them defensively for paths with spaces).
        return f'"{sys.executable}"'
    # Source mode — launch with the same Python that is currently running.
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{sys.executable}" "{main_py}"'


def is_enabled() -> bool:
    """Return True if the autostart registry entry exists for this app."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> None:
    """Add / update the autostart registry entry."""
    cmd = _exe_command()
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)


def disable() -> None:
    """Remove the autostart registry entry if it exists."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _APP_NAME)
    except FileNotFoundError:
        pass  # already absent — that's fine
    except OSError:
        pass


def apply(enabled: bool) -> None:
    """Enable or disable autostart based on a boolean flag."""
    if enabled:
        enable()
    else:
        disable()
