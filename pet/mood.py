"""
mood.py — Pet mood tracker.

Moods:
  HAPPY   — just interacted (chat/treat/fetch). Lasts 10 min.
  EXCITED — received a treat or playing fetch. Lasts 5 min.
  NEUTRAL — default calm state.
  LONELY  — no interaction for 30+ min. Buddy craves attention.

Mood is exposed to main.py which adjusts the SLM system prompt and
may trigger a loneliness speech bubble.
"""

from __future__ import annotations
import time
from enum import Enum, auto

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class PetMood(Enum):
    HAPPY   = auto()
    EXCITED = auto()
    NEUTRAL = auto()
    LONELY  = auto()

    def description(self) -> str:
        return {
            PetMood.HAPPY:   "happy and content after a nice chat",
            PetMood.EXCITED: "super excited and bouncy — just got a treat or played fetch",
            PetMood.NEUTRAL: "calm and attentive",
            PetMood.LONELY:  "a little lonely and really craving attention from their owner",
        }[self]


class MoodTracker(QObject):
    """Tracks Buddy's emotional state and emits mood_changed when it shifts."""

    mood_changed = pyqtSignal(object)   # PetMood

    LONELY_THRESHOLD_MIN = 30
    HAPPY_DURATION_MIN   = 10
    EXCITED_DURATION_MIN = 5

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mood              = PetMood.NEUTRAL
        self._last_interaction  = time.monotonic()
        self._mood_until        = 0.0   # monotonic time when elevated mood expires
        self._lonely_notified   = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30_000)   # check every 30 s

    # ── Public ──────────────────────────────────────────────────────────

    @property
    def mood(self) -> PetMood:
        return self._mood

    def on_interacted(self) -> None:
        """Call when user chats with Buddy (double-click dialog)."""
        self._last_interaction = time.monotonic()
        self._mood_until       = time.monotonic() + self.HAPPY_DURATION_MIN * 60
        self._lonely_notified  = False
        self._set(PetMood.HAPPY)

    def on_treat(self) -> None:
        """Call when user gives Buddy a treat."""
        self._last_interaction = time.monotonic()
        self._mood_until       = time.monotonic() + self.EXCITED_DURATION_MIN * 60
        self._lonely_notified  = False
        self._set(PetMood.EXCITED)

    def on_fetch(self) -> None:
        """Call when fetch game starts."""
        self._last_interaction = time.monotonic()
        self._mood_until       = time.monotonic() + self.EXCITED_DURATION_MIN * 60
        self._lonely_notified  = False
        self._set(PetMood.EXCITED)

    # ── Internal ─────────────────────────────────────────────────────────

    def _tick(self) -> None:
        now = time.monotonic()

        # Elevated mood expired → return to neutral
        if self._mood in (PetMood.HAPPY, PetMood.EXCITED) and now > self._mood_until:
            self._set(PetMood.NEUTRAL)
            return

        # Check for loneliness (only from NEUTRAL)
        if self._mood == PetMood.NEUTRAL:
            elapsed_min = (now - self._last_interaction) / 60
            if elapsed_min >= self.LONELY_THRESHOLD_MIN and not self._lonely_notified:
                self._lonely_notified = True
                self._set(PetMood.LONELY)

    def _set(self, mood: PetMood) -> None:
        if mood != self._mood:
            self._mood = mood
            self.mood_changed.emit(mood)
