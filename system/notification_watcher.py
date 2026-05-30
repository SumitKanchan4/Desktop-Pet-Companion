"""
notification_watcher.py — Watches the Windows notification database for new toasts.

Polls wpndatabase.db (opened read-only / immutable so it never conflicts with
the live WpnService lock) every 8 seconds.  Emits new_notification(app, title, body)
for each new toast that arrives while Buddy is running.

No extra dependencies — uses only stdlib sqlite3 + xml.etree.
"""

from __future__ import annotations
import os
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Notifications/wpndatabase.db"


class NotificationWatcher(QObject):
    """Polls the Windows toast notification DB; emits new_notification on new items."""

    new_notification = pyqtSignal(str, str, str)   # app_name, title, body

    def __init__(self, poll_ms: int = 8000) -> None:
        super().__init__()
        self._last_id  = self._current_max_id()   # start from NOW — ignore old ones
        self._timer    = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(poll_ms)

    # ── DB helpers ────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Open the live DB read-only without blocking the Windows service."""
        return sqlite3.connect(
            f"file:{_DB}?mode=ro&immutable=1", uri=True, timeout=2
        )

    def _current_max_id(self) -> int:
        """Return the highest notification Id already in the DB (skip old ones)."""
        if not _DB.exists():
            return 0
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT MAX(Id) FROM Notification").fetchone()
                return row[0] if row and row[0] else 0
        except Exception:
            return 0

    # ── Poll ─────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        if not _DB.exists():
            return
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT n.Id, h.PrimaryId, n.Payload "
                    "FROM Notification n "
                    "LEFT JOIN NotificationHandler h ON h.RecordId = n.HandlerId "
                    "WHERE n.Id > ? "
                    "ORDER BY n.Id ASC LIMIT 10",
                    (self._last_id,),
                ).fetchall()
        except Exception:
            return

        for nid, app_id, payload in rows:
            self._last_id = max(self._last_id, nid)
            app, title, body = self._parse(app_id or "", payload or "")
            if title:
                self.new_notification.emit(app, title, body)

    # ── Parser ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse(app_id: str, payload: str | bytes) -> tuple[str, str, str]:
        # Friendly app name from PrimaryId
        # e.g. "Microsoft.Outlook_8wekyb!Outlook" → "Outlook"
        #      "C:\Program Files\...\Teams.exe"   → "Teams"
        if "!" in app_id:
            app = app_id.split("!")[-1]
        elif "\\" in app_id or "/" in app_id:
            app = Path(app_id.replace("/", "\\")).stem
        else:
            app = app_id or "App"

        title, body = "", ""
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", errors="ignore")
            # Strip null bytes that some apps embed
            payload = payload.replace("\x00", "")
            root   = ET.fromstring(payload)
            texts  = [t.text or "" for t in root.findall(".//text")]
            if texts:
                title = texts[0].strip()
            if len(texts) > 1:
                body = texts[1].strip()
        except ET.ParseError:
            pass

        return app, title, body

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._timer.stop()
