"""
system/updater.py — Background update checker.

Polls the GitHub Releases API once per session (and again every 24 h) to
see if a newer version tag exists.  Runs entirely on a daemon thread so
the main/UI thread is never blocked.

Usage
-----
    from system.updater import UpdateChecker
    checker = UpdateChecker(on_update_available=_my_callback)
    checker.start()          # fire-and-forget; auto-repeats every 24 h

The callback receives (latest_version: str, download_url: str) and is
posted to the Qt main thread via a QMetaObject call so it is safe to
update the UI directly.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen, Request

from PyQt6.QtCore import QObject, pyqtSignal

from system.version import APP_VERSION, GITHUB_REPO

_API_URL   = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_CHECK_INTERVAL = 24 * 60 * 60   # seconds between repeat checks
_TIMEOUT   = 8                    # seconds for the HTTP request


def _parse_version(tag: str) -> tuple[int, ...]:
    """Convert 'v1.2.3' or '1.2.3' to (1, 2, 3) for comparison."""
    return tuple(int(x) for x in tag.lstrip("v").split(".") if x.isdigit())


class UpdateChecker(QObject):
    """
    QObject wrapper so the result can be delivered as a Qt signal.

    ``update_available`` is emitted on the Qt main thread with
    (latest_version, html_download_url).
    """

    update_available = pyqtSignal(str, str)   # (version_str, download_url)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the background daemon thread (idempotent)."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="updater")
        self._thread.start()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        """Run forever: check → sleep 24 h → check again."""
        while True:
            self._check_once()
            time.sleep(_CHECK_INTERVAL)

    def _check_once(self) -> None:
        try:
            req = Request(
                _API_URL,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": f"DesktopPetBuddy/{APP_VERSION}"},
            )
            with urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())

            latest_tag = data.get("tag_name", "")
            html_url   = data.get("html_url", "")
            if not latest_tag:
                return

            if _parse_version(latest_tag) > _parse_version(APP_VERSION):
                # Emit on the Qt main thread
                self.update_available.emit(latest_tag.lstrip("v"), html_url)

        except (URLError, OSError, ValueError, KeyError):
            pass   # network unavailable or malformed JSON — silently skip
