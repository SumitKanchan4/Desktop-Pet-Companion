"""
pet_state.py — State machine for the desktop pet.

States map directly to sprite animation names and drive movement logic.
Transitions are triggered by:
  - context changes (from ContextDetector)
  - throttle level changes (from ResourceMonitor)
  - user interactions (click, drag)
  - timers (wander, idle timeout, break reminder)
"""

from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass, field
import random
import time

from system.context_detector import PetContext
from system.throttle import ThrottleLevel


class PetState(Enum):
    IDLE     = auto()   # standing still, blinking
    WALK     = auto()   # wandering around
    RUN      = auto()   # chasing cursor / excited burst
    SLEEP    = auto()   # curled up, system overloaded or long idle
    WATCH    = auto()   # watching video / meeting
    EXCITED  = auto()   # pet just got clicked / greeted
    GRABBED  = auto()   # user is dragging
    DANCE    = auto()   # music playing
    # Phase 1 — expressive behaviours
    SIT      = auto()   # sitting attentively
    JUMP     = auto()   # jumping (PetWindow drives the parabola)
    PAW      = auto()   # batting front paw at screen edge
    SCRATCH  = auto()   # scratching ear with raised hind leg
    STRETCH  = auto()   # waking / boredom body-stretch


# Maps state -> sprite sheet name suffix (direction appended by engine)
STATE_SPRITE: dict[PetState, str] = {
    PetState.IDLE:    "idle",
    PetState.WALK:    "walk",
    PetState.RUN:     "run",
    PetState.SLEEP:   "sleep",
    PetState.WATCH:   "watch",
    PetState.EXCITED: "excited",
    PetState.GRABBED: "grabbed",
    PetState.DANCE:   "dance",
    # Phase 1
    PetState.SIT:     "sit",
    PetState.JUMP:    "jump",
    PetState.PAW:     "paw",
    PetState.SCRATCH: "scratch",
    PetState.STRETCH: "stretch",
}

# States that need _right / _left suffix (directional facing)
DIRECTIONAL_STATES = {PetState.WALK, PetState.RUN,
                       PetState.SIT, PetState.JUMP, PetState.PAW}


@dataclass
class PetBrain:
    """
    Manages state transitions for the pet.
    Called each tick and on events; returns the resolved PetState.
    """

    context:  PetContext   = PetContext.UNKNOWN
    throttle: ThrottleLevel = ThrottleLevel.FULL

    _state:       PetState = field(default=PetState.IDLE, init=False)
    _state_since: float    = field(default_factory=time.monotonic, init=False)
    _grabbed:     bool     = field(default=False, init=False)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> PetState:
        return self._state

    def on_context_changed(self, ctx: PetContext) -> None:
        self.context = ctx
        self._resolve()

    def on_throttle_changed(self, level: ThrottleLevel) -> None:
        self.throttle = level
        self._resolve()

    def on_grab_start(self) -> None:
        self._grabbed = True
        self._transition(PetState.GRABBED)

    def on_grab_end(self) -> None:
        self._grabbed = False
        self._resolve()

    def force_run(self) -> None:
        """Override state to RUN for chase sequences."""
        self._transition(PetState.RUN)

    def on_click(self) -> None:
        if not self._grabbed:
            self._transition(PetState.EXCITED)

    def tick(self) -> None:
        """Call periodically (every wander_interval_s) to drive autonomous behaviour."""
        if self._grabbed:
            return
        elapsed = time.monotonic() - self._state_since

        # EXCITED expires after 2 s
        if self._state == PetState.EXCITED and elapsed > 2:
            self._resolve()
            return

        # JUMP is owned by PetWindow physics — never interrupt it here
        if self._state == PetState.JUMP:
            return

        # Throttle-forced sleep overrides everything except active grab
        if self.throttle == ThrottleLevel.SLEEP:
            self._transition(PetState.SLEEP)
            return

        # Auto-exit from timed expressive states
        if self._state == PetState.SIT and elapsed > 8:
            self._resolve()   # return to context-appropriate state
            return
        if self._state in (PetState.SCRATCH, PetState.STRETCH) and elapsed > 4:
            self._transition(PetState.IDLE)
            return
        if self._state == PetState.PAW and elapsed > 2.5:
            self._transition(PetState.IDLE)
            return
        # Don't tick further while mid-animation
        if self._state in (PetState.SIT, PetState.SCRATCH,
                           PetState.STRETCH, PetState.PAW):
            return

        # Context-driven transitions
        desired = self._desired_state()
        if desired != self._state:
            self._transition(desired)
        elif self._state == PetState.WALK and elapsed > 4:
            # Pause fairly often — makes the pet feel natural
            if random.random() < 0.55:
                self._transition(PetState.IDLE)
        elif self._state == PetState.IDLE and elapsed > 6:
            # Randomly pick an idle behaviour or resume walking
            r = random.random()
            if r < 0.25:
                self._transition(PetState.SIT)      # 25 % sit down
            elif r < 0.40:
                self._transition(PetState.SCRATCH)  # 15 % scratch ear
            elif r < 0.48:
                self._transition(PetState.STRETCH)  #  8 % stretch
            elif r < 0.68:
                self._transition(PetState.WALK)     # 20 % resume walk

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _resolve(self) -> None:
        """Re-evaluate state from current context and throttle."""
        if self._grabbed:
            return
        self._transition(self._desired_state())

    def _desired_state(self) -> PetState:
        # Throttle overrides take highest priority
        if self.throttle == ThrottleLevel.SLEEP:
            return PetState.SLEEP
        if self.throttle == ThrottleLevel.MINIMAL:
            return PetState.IDLE  # freeze, use cheapest animation

        # Context-driven
        ctx_map = {
            PetContext.WATCHING: PetState.WATCH,
            PetContext.MEETING:  PetState.SLEEP,  # shh, meeting in progress
            PetContext.MUSIC:    PetState.DANCE,
            PetContext.GAMING:   PetState.EXCITED,
            PetContext.CODING:   PetState.WALK,   # wanders while you code
            PetContext.TERMINAL: PetState.WATCH,
            PetContext.BROWSING: PetState.IDLE,
            PetContext.IDLE:     PetState.SLEEP,
            PetContext.UNKNOWN:  PetState.WALK,
        }
        return ctx_map.get(self.context, PetState.WALK)

    def _transition(self, new_state: PetState) -> None:
        if new_state != self._state:
            self._state = new_state
            self._state_since = time.monotonic()

    # ------------------------------------------------------------------ #
    # Phase 1 public API                                                   #
    # ------------------------------------------------------------------ #

    def do_jump(self) -> None:
        """Trigger a jump. PetWindow drives the parabola and calls on_jump_landed."""
        if not self._grabbed:
            self._transition(PetState.JUMP)

    def on_jump_landed(self) -> None:
        """Called by PetWindow when the jump arc completes."""
        if self._state == PetState.JUMP:
            self._resolve()

    def do_paw(self) -> None:
        """Trigger the screen-edge paw animation (called from PetWindow)."""
        if self._state not in (PetState.GRABBED, PetState.SLEEP, PetState.JUMP):
            self._transition(PetState.PAW)
