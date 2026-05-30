"""
throttle.py — Monitors CPU and RAM usage, emits a ThrottleLevel signal.
Pet engine subscribes to this to adjust FPS, LLM calls, and movement.

Levels:
  FULL    — system is free, pet operates at full capability
  REDUCED — moderate load, halve FPS, pause LLM
  MINIMAL — high load, freeze animation, disable everything non-visual
  SLEEP   — extreme load, pet sleeps silently
"""

from __future__ import annotations
from enum import Enum, auto

import psutil
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class ThrottleLevel(Enum):
    FULL    = auto()
    REDUCED = auto()
    MINIMAL = auto()
    SLEEP   = auto()


class ResourceMonitor(QObject):
    """Polls system resources and emits level_changed when throttle level shifts."""

    level_changed = pyqtSignal(object)   # emits ThrottleLevel

    def __init__(self, cfg: dict, parent: QObject | None = None) -> None:
        super().__init__(parent)
        t = cfg.get("throttle", {})
        self._interval_ms   = int(t.get("check_interval_s", 10) * 1000)
        self._full_cpu      = t.get("full",    {}).get("cpu_max",          40)
        self._full_ram      = t.get("full",    {}).get("ram_free_min_gb", 2.0)
        self._reduced_cpu   = t.get("reduced", {}).get("cpu_max",          70)
        self._reduced_ram   = t.get("reduced", {}).get("ram_free_min_gb", 1.0)
        self._minimal_cpu   = t.get("minimal", {}).get("cpu_max",          90)
        self._minimal_ram   = t.get("minimal", {}).get("ram_free_min_gb", 0.5)

        self._current_level = ThrottleLevel.FULL
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        # Prime psutil so first call isn't blocking
        psutil.cpu_percent(interval=None)

    def start(self) -> None:
        self._timer.start(self._interval_ms)

    def stop(self) -> None:
        self._timer.stop()

    @property
    def level(self) -> ThrottleLevel:
        return self._current_level

    def _check(self) -> None:
        cpu  = psutil.cpu_percent(interval=None)          # non-blocking
        ram  = psutil.virtual_memory().available / (1024 ** 3)  # GB free

        if cpu > self._minimal_cpu or ram < self._minimal_ram:
            new_level = ThrottleLevel.SLEEP
        elif cpu > self._reduced_cpu or ram < self._reduced_ram:
            new_level = ThrottleLevel.MINIMAL
        elif cpu > self._full_cpu or ram < self._full_ram:
            new_level = ThrottleLevel.REDUCED
        else:
            new_level = ThrottleLevel.FULL

        if new_level != self._current_level:
            self._current_level = new_level
            self.level_changed.emit(new_level)
