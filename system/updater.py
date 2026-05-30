"""
system/updater.py — Background update checker and silent downloader.

Flow:
  1. Poll GitHub Releases API at startup, then every 24 h.
  2. If a newer version exists, find the .exe asset and download it in the
     background to the system temp folder.
  3. Emit ``download_complete(version, local_path)`` on the Qt main thread.
  4. Caller shows a "ready to install" dialog; if the user accepts, launch
     the installer and quit the app.

All network and disk I/O is on daemon threads — the UI thread is never blocked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen, Request

from PyQt6.QtCore import QObject, pyqtSignal

from system.version import APP_VERSION, GITHUB_REPO

_API_URL        = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_CHECK_INTERVAL = 24 * 60 * 60   # seconds between repeat checks
_TIMEOUT        = 15              # seconds for each HTTP request
_ASSET_SUFFIX   = ".exe"         # we only care about the Windows installer


def _parse_version(tag: str) -> tuple[int, ...]:
    """Convert 'v1.2.3' or '1.2.3' to (1, 2, 3) for safe numeric comparison."""
    return tuple(int(x) for x in tag.lstrip("v").split(".") if x.isdigit())


class UpdateChecker(QObject):
    """
    Checks for updates and downloads the installer silently.

    Signals emitted on the Qt main thread:
      download_started(version)          — download has begun
      download_complete(version, path)   — installer is ready at `path`
      download_failed(version, reason)   — download failed (network error etc.)
    """

    download_started  = pyqtSignal(str)        # version
    download_complete = pyqtSignal(str, str)   # (version, local_installer_path)
    download_failed   = pyqtSignal(str, str)   # (version, error_message)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._check_thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the background daemon thread (idempotent)."""
        if self._check_thread and self._check_thread.is_alive():
            return
        self._check_thread = threading.Thread(
            target=self._loop, daemon=True, name="updater-check"
        )
        self._check_thread.start()

    @staticmethod
    def launch_installer(path: str) -> None:
        """
        Launch the downloaded installer and quit the running app.
        Safe to call from the main thread.
        """
        subprocess.Popen([path])   # Inno Setup installer runs its own UAC prompt
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        """Run forever: check → (download if newer) → sleep 24 h → repeat."""
        while True:
            self._check_once()
            time.sleep(_CHECK_INTERVAL)

    def _check_once(self) -> None:
        try:
            req = Request(
                _API_URL,
                headers={
                    "Accept":     "application/vnd.github+json",
                    "User-Agent": f"DesktopPetBuddy/{APP_VERSION}",
                },
            )
            with urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())

            latest_tag = data.get("tag_name", "")
            if not latest_tag:
                return

            if _parse_version(latest_tag) <= _parse_version(APP_VERSION):
                return  # already up to date

            version = latest_tag.lstrip("v")

            # Find the Windows installer asset
            asset_url = None
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(_ASSET_SUFFIX) and "Setup" in name:
                    asset_url = asset.get("browser_download_url", "")
                    break

            if not asset_url:
                # Release exists but no installer asset yet — nothing to download
                return

            # Kick off the download on a separate thread so the check loop
            # returns immediately and the 24-h sleep is not delayed.
            threading.Thread(
                target=self._download,
                args=(version, asset_url),
                daemon=True,
                name="updater-download",
            ).start()

        except (URLError, OSError, ValueError, KeyError):
            pass   # network unavailable or malformed JSON — silently skip

    def _download(self, version: str, url: str) -> None:
        """Stream the installer to a temp file and emit the result."""
        dest = os.path.join(tempfile.gettempdir(), f"BuddySetup-{version}.exe")

        # If a previous run already downloaded this exact version, reuse it.
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            self.download_complete.emit(version, dest)
            return

        self.download_started.emit(version)

        try:
            req = Request(
                url,
                headers={"User-Agent": f"DesktopPetBuddy/{APP_VERSION}"},
            )
            with urlopen(req, timeout=_TIMEOUT) as resp, open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)

            self.download_complete.emit(version, dest)

        except (URLError, OSError) as exc:
            # Clean up partial file
            try:
                os.remove(dest)
            except OSError:
                pass
            self.download_failed.emit(version, str(exc))

