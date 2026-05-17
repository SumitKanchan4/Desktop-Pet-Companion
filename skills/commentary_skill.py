"""commentary_skill.py — Context reactions, SLM commentary, idle behaviors, and greetings."""
from __future__ import annotations

import datetime
import random
import time

from PyQt6.QtGui import QCursor

from audio import engine as sound_engine
from system.context_detector import PetContext
from system.throttle import ThrottleLevel


class CommentarySkill:
    """Drives context reactions, SLM commentary, break reminders, idle behaviours, and greetings."""

    def __init__(self, window, slm, brain, ctx, monitor, cfg: dict, username: str) -> None:
        self._window   = window
        self._slm      = slm
        self._brain    = brain
        self._ctx      = ctx
        self._monitor  = monitor
        self._cfg      = cfg
        self._username = username

        self._quiet          = False
        self._prev_ctx       = PetContext.UNKNOWN
        self._focus_start    = time.monotonic()
        self._last_comment   = time.monotonic()
        self._last_ctx_react = 0.0
        self._break_warned   = False

    # ── Public state ──────────────────────────────────────────────────────────

    @property
    def quiet(self) -> bool:
        """True while Buddy is suppressed (e.g. during meetings)."""
        return self._quiet

    # ── Context reactions ─────────────────────────────────────────────────────

    def on_context_changed(self, ctx: PetContext) -> None:
        now  = time.monotonic()
        prev = self._prev_ctx
        self._prev_ctx = ctx

        if ctx != PetContext.CODING:
            self._focus_start = time.monotonic()
            self._break_warned = False

        # ── Entering meeting: go quiet ────────────────────────────────────────
        if ctx == PetContext.MEETING:
            self._quiet = True
            if not self._window._bubble:
                self._window.say(
                    f"Shhh! I'll be quiet during your meeting, {self._username} 🤫",
                    duration_ms=4000,
                )
            return

        # ── Leaving meeting: resume ───────────────────────────────────────────
        if prev == PetContext.MEETING:
            self._quiet = False
            self._window.say(
                f"Meeting over! *wags tail happily* How'd it go, {self._username}? 🐾",
                duration_ms=5000,
            )
            return

        self._quiet = False

        # ── Context-specific reactions (60 s cooldown) ────────────────────────
        _REACT = {
            PetContext.GAMING:   f"Gaming time, {self._username}?! I'll cheer for you! 🎮 Let's GOOO!",
            PetContext.MUSIC:    f"*ears perk up* Ooh, music! *starts wiggling* 🎵",
            PetContext.WATCHING: f"Ooh, watching something? I'll sit right here with you 👀",
        }
        if ctx in _REACT and not self._window._bubble and (now - self._last_ctx_react) > 60:
            self._last_ctx_react = now
            if self._slm.available:
                self._slm.ask(
                    f"User just switched to {ctx.name.lower()} — react in-character with excitement!",
                    on_done=self._window.say,
                    track_history=False,
                )
            else:
                self._window.say(_REACT[ctx], duration_ms=5000)
            return

        # ── Generic 7 % SLM commentary for other contexts (10 min cooldown) ──
        if (self._monitor.level == ThrottleLevel.FULL
                and random.random() < 0.07
                and not self._window._bubble
                and (now - self._last_comment) > 600):
            self._last_comment = now
            self._slm.context_comment(
                ctx.name, self._ctx.window_title,
                on_done=self._window.say,
            )

    # ── Periodic commentary ───────────────────────────────────────────────────

    def maybe_comment(self) -> None:
        """Timer callback: fire an SLM context comment when conditions allow."""
        if self._quiet:
            return
        if self._monitor.level not in (ThrottleLevel.FULL, ThrottleLevel.REDUCED):
            return
        now = time.monotonic()
        if (now - self._last_comment) < 600:
            return
        ctx   = self._ctx.context
        title = self._ctx.window_title
        if ctx == PetContext.UNKNOWN:
            return
        self._last_comment = now
        self._slm.context_comment(ctx.name, title, on_done=self._window.say)

    # ── Idle behaviours ───────────────────────────────────────────────────────

    def do_idle_behavior(self, treat_active: bool) -> None:
        """Random idle animation so Buddy feels alive between events."""
        if (self._quiet or treat_active
                or self._window._is_dragging or self._window._bubble):
            return
        behaviors = [
            ("*yawns* 😴 ...zZz...",           "none"),
            ("*scratches ear* 🐾",             "none"),
            ("*sniffs the air curiously* 👃",  "sniff"),
            ("*does a big stretch* 🐶",        "none"),
            ("*wags tail for no reason* 🐾",   "none"),
            ("*stares at nothing* 👁️",         "none"),
        ]
        text, snd = random.choice(behaviors)
        if snd == "sniff":
            sound_engine.sniff()
        self._window.say(text, duration_ms=3000, sound="none")

    def maybe_follow_cursor(self, treat_active: bool) -> None:
        """Occasionally wander toward mouse cursor (30 % chance)."""
        if (treat_active or self._window._is_dragging
                or self._window._bubble or self._quiet):
            return
        if random.random() < 0.30:
            self._window.walk_toward(QCursor.pos())

    # ── Break reminder ────────────────────────────────────────────────────────

    def check_break(self) -> None:
        if self._quiet or self._ctx.context != PetContext.CODING:
            return
        if self._monitor.level == ThrottleLevel.SLEEP:
            return
        elapsed_min = int((time.monotonic() - self._focus_start) / 60)
        if elapsed_min >= 45 and not self._break_warned:
            self._break_warned = True
            self._slm.break_reminder(elapsed_min, self._username, on_done=self._window.say)

    # ── Startup greeting ──────────────────────────────────────────────────────

    def greet(self, weather=None) -> None:
        """Say a time-appropriate greeting, optionally including weather context."""
        name = self._username
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            fallback = f"Good morning, {name}! ☀️ Ready to have a great day?"
            time_ctx = "morning"
        elif 12 <= hour < 17:
            fallback = f"Hey {name}! Good afternoon! Let's get things done! 🌤️"
            time_ctx = "afternoon"
        elif 17 <= hour < 21:
            fallback = f"Good evening, {name}! 🌆 Still hard at work?"
            time_ctx = "evening"
        else:
            fallback = f"Hey {name}... 🌙 You're up late! Don't overwork yourself!"
            time_ctx = "late night"

        if self._slm.available:
            weather_ctx = (
                f" Weather outside: {weather.buddy_summary()}." if weather else ""
            )
            self._slm.ask(
                f"Greet your owner {name} warmly — it's {time_ctx}.{weather_ctx} Keep it short and cute.",
                on_done=self._window.say,
            )
        else:
            self._window.say(fallback)
