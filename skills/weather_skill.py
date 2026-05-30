"""weather_skill.py — Weather awareness: fetches conditions and has Buddy react."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class WeatherSkill(QObject):
    """Fetches weather via wttr.in and reacts to current conditions on first fetch."""

    _raw = pyqtSignal(object)   # background thread → Qt thread bridge

    def __init__(self, window, slm) -> None:
        super().__init__()
        self._window  = window
        self._slm     = slm
        self._weather = None
        self._raw.connect(self._on_update)

    # ── Thread-safe callback (background fetch → Qt thread) ──────────────────

    def background_cb(self, data) -> None:
        """Called from background fetch thread; re-emits on Qt thread."""
        self._raw.emit(data)

    def _on_update(self, data) -> None:
        if data is None:
            return
        first = self._weather is None
        self._weather = data
        if first:
            QTimer.singleShot(8_000, self._say_weather)

    def _say_weather(self) -> None:
        if self._weather is None or self._window._bubble:
            return
        msg, snd = self._weather.buddy_reaction()
        self._window.say(msg, duration_ms=6000, sound=snd)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def data(self):
        """Current WeatherData, or None if not yet fetched."""
        return self._weather
