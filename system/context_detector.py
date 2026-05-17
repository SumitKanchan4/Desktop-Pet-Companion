"""
context_detector.py — Polls the active foreground window every ~1.5s.
Maps process name + window title to a PetContext label.
Emits context_changed(PetContext) signal when context shifts.
"""

from __future__ import annotations
from enum import Enum, auto

import psutil
import win32gui
import win32process

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class PetContext(Enum):
    CODING   = auto()
    WATCHING = auto()
    MEETING  = auto()
    MUSIC    = auto()
    GAMING   = auto()
    BROWSING = auto()
    TERMINAL = auto()
    IDLE     = auto()   # lock screen / no foreground window
    UNKNOWN  = auto()


class ContextDetector(QObject):
    """Detects foreground window and emits context_changed when it shifts."""

    context_changed = pyqtSignal(object)  # emits PetContext
    window_title_changed = pyqtSignal(str)

    def __init__(self, cfg: dict, parent: QObject | None = None) -> None:
        super().__init__(parent)
        ctx_cfg = cfg.get("context", {})
        self._interval_ms = int(ctx_cfg.get("poll_interval_s", 1.5) * 1000)
        self._rules: dict[str, list[str]] = ctx_cfg.get("rules", {})

        self._current_context = PetContext.UNKNOWN
        self._current_title   = ""

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        self._timer.start(self._interval_ms)

    def stop(self) -> None:
        self._timer.stop()

    @property
    def context(self) -> PetContext:
        return self._current_context

    @property
    def window_title(self) -> str:
        return self._current_title

    def _poll(self) -> None:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                self._update(PetContext.IDLE, "")
                return

            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc_name = psutil.Process(pid).name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc_name = ""

            new_context = self._classify(proc_name, title.lower())
            self._update(new_context, title)

        except Exception:
            pass  # never crash the pet due to window detection

    def _classify(self, proc: str, title: str) -> PetContext:
        for label, fragments in self._rules.items():
            for frag in fragments:
                if frag in proc or frag in title:
                    return PetContext[label.upper()]
        return PetContext.UNKNOWN

    def _update(self, ctx: PetContext, title: str) -> None:
        if ctx != self._current_context:
            self._current_context = ctx
            self.context_changed.emit(ctx)
        if title != self._current_title:
            self._current_title = title
            self.window_title_changed.emit(title)
