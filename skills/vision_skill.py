"""vision_skill.py — Screen vision: lets Buddy observe and comment on the screen."""
from __future__ import annotations

import time

from PyQt6.QtCore import QObject, pyqtSignal

from audio import engine as sound_engine
from intelligence import screen_vision


class VisionSkill(QObject):
    """Manages screen vision peeks using a multimodal model (moondream or fallback)."""

    _raw = pyqtSignal(str)   # background thread → Qt thread bridge

    def __init__(self, cfg: dict, window) -> None:
        super().__init__()
        self._window      = window
        self._last_vision = 0.0
        self._manual      = False
        self._raw.connect(self._on_result)
        screen_vision.configure(cfg)   # apply vision_model from config.yaml

    # ── Thread-safe callback ──────────────────────────────────────────────────

    def background_cb(self, text: str | None) -> None:
        """Called from background thread; re-emits on Qt thread."""
        self._raw.emit(text or "")

    # ── Peek triggers ─────────────────────────────────────────────────────────

    def do_peek(self) -> None:
        """Manual peek triggered from tray menu (30 s re-trigger guard)."""
        now = time.monotonic()
        if now - self._last_vision < 30:
            return
        self._last_vision = now
        self._window.say("*squints at screen* 👁️ Lemme look…", duration_ms=2500, sound="none")
        self._manual = True
        screen_vision.peek(self.background_cb)

    def auto_peek(self, quiet: bool, busy: bool) -> None:
        """Timer-driven auto-peek — suppressed when quiet or busy (12 min minimum gap)."""
        if quiet or busy:
            return
        now = time.monotonic()
        if now - self._last_vision < 12 * 60:
            return
        self._last_vision = now
        self._manual = False
        screen_vision.peek(self.background_cb)

    # ── Result handler (Qt thread) ────────────────────────────────────────────

    def _on_result(self, text: str) -> None:
        if not text:
            if self._manual:
                self._window.say(
                    "I need glasses! 🐶 Run:  ollama pull moondream",
                    duration_ms=7000, sound="none",
                )
            return
        sound_engine.excited_yip(count=1)
        self._window.say(text, duration_ms=6000)
