"""play_skill.py — Treat, fetch, and ball physics interactions."""
from __future__ import annotations

import random

from PyQt6.QtCore import QPoint, QTimer

from audio import engine as sound_engine
from ui.treat_widget import spawn_treat, spawn_fetch
from ui.ball_widget import BallWidget


class PlaySkill:
    """Manages treat drops, fetch throws, and the bouncy ball mini-game."""

    _BALL_MAX_KICKS = 6
    _BALL_DURATION_MS = 35_000

    def __init__(self, window, brain, mood, cfg: dict, username: str) -> None:
        self._window     = window
        self._brain      = brain
        self._mood       = mood
        self._cfg        = cfg
        self._username   = username
        self._treat      = None   # active TreatWidget or None
        self._ball       = None   # active BallWidget or None
        self._ball_kicks = 0

    # ── Public state accessors ────────────────────────────────────────────────

    @property
    def active_treat(self):
        return self._treat

    @property
    def active_ball(self):
        return self._ball

    # ── Ball mini-game ────────────────────────────────────────────────────────

    def on_spawn_ball(self) -> None:
        """Spawn a bouncy ball for Buddy to chase and kick."""
        if self._ball is not None or self._treat is not None:
            return
        sx = self._window._screen_rect.width()
        sy = self._window._screen_rect.height()
        bx = random.randint(sx // 4, 3 * sx // 4)
        by = random.randint(sy // 4, 3 * sy // 4)
        self._ball = BallWidget(self._window._screen_rect, QPoint(bx, by))
        self._ball_kicks = 0
        self._mood.on_fetch()
        self._window.chase(self._ball.centre())
        self._window.say("🎱 BALL!! *launches self at it*", duration_ms=3000, sound="yip")
        QTimer.singleShot(self._BALL_DURATION_MS, self.end_ball_play)

    def ball_track_step(self) -> None:
        """Keep Buddy's chase target locked onto the moving ball (called every 80 ms)."""
        if self._ball is None:
            return
        if self._window._chase_target is not None:
            self._window._chase_target = self._ball.centre()

    def end_ball_play(self) -> None:
        if self._ball is None:
            return
        self._ball.vanish()
        self._ball = None
        self._window.stop_chase()
        endings = [
            "*pants happily* That was FUN! 🎱",
            "Best. Ball. Ever. 🐾 I need a nap now...",
            f"More ball time please, {self._username}! 🎱",
        ]
        self._window.say(random.choice(endings), duration_ms=4000, sound="none")

    # ── Treat & fetch ─────────────────────────────────────────────────────────

    def on_give_treat(self) -> None:
        """Drop a bone near Buddy; Buddy runs to it."""
        if self._treat is not None:
            return
        self._mood.on_treat()
        self._treat = spawn_treat(self._window._pos, self._window._screen_rect)
        sound_engine.sniff()
        self._window.chase(self._treat.centre())

    def on_play_fetch(self) -> None:
        """Throw bone to a far spot; Buddy chases after it lands."""
        if self._treat is not None:
            return
        self._mood.on_fetch()
        widget, landing = spawn_fetch(self._window._pos, self._window._screen_rect)
        self._treat = widget
        self._treat.landed.connect(lambda centre: self._window.chase(centre))
        self._treat.throw_to(landing, duration_ms=900)
        self._window.say("*catches the scent* FETCH! 🎾", duration_ms=3000)

    def on_treat_reached(self) -> None:
        """Buddy reached the target — kick the ball or eat the treat."""
        # ── Ball mode: kick and keep chasing ─────────────────────────────────
        if self._ball is not None:
            pet_cx = self._window._pos.x() + (self._window.FRAME_W * self._window.SCALE) / 2
            pet_cy = self._window._pos.y() + (self._window.FRAME_H * self._window.SCALE) / 2
            self._ball.kick(pet_cx, pet_cy)
            self._ball_kicks += 1
            sound_engine.excited_yip(count=1)
            if self._ball_kicks >= self._BALL_MAX_KICKS:
                self.end_ball_play()
            else:
                self._window.chase(self._ball.centre())
            return

        # ── Treat / fetch mode ────────────────────────────────────────────────
        if self._treat:
            self._treat.vanish()
            self._treat = None
        self._brain.on_click()
        sound_engine.excited_yip(count=2)
        treats = [
            "Woof! Got it! 🐾 Yummy!",
            "Nom nom nom! 🦴 Best treat ever!",
            "*tail wag intensifies* YESSS!",
            f"Thank you {self._username}! You're the best!",
        ]
        self._window.say(random.choice(treats), duration_ms=5000)
