"""social_skill.py — Petting, mood reactions, and notification responses."""
from __future__ import annotations

import random

from audio import engine as sound_engine
from pet.mood import PetMood


class SocialSkill:
    """Handles social interactions: petting, mood shifts, and system notifications."""

    def __init__(self, window, slm, mood, username: str) -> None:
        self._window   = window
        self._slm      = slm
        self._mood     = mood
        self._username = username

    def on_petted(self) -> None:
        self._mood.on_interacted()
        sound_engine.excited_yip(count=1)
        self._window.do_jump()   # happy jump
        pets = [
            "❤️ *melts* ...more please!!",
            f"❤️❤️ Best pets ever, {self._username}!",
            "*tail wag intensifies* ❤️ Don't stop!",
            "Woof ❤️ You're my favourite human!",
        ]
        self._window.say(random.choice(pets), duration_ms=4000, sound="none")

    def on_mood_changed(self, mood: PetMood) -> None:
        self._slm.set_mood(mood.description())
        if mood == PetMood.LONELY:
            loneliness = [
                f"*whimpers softly* {self._username}... you've been ignoring me... 😢",
                f"Buddy misses you, {self._username}! Pet me please! 🐾",
                f"*sits by your cursor waiting patiently* ...{self._username}?",
            ]
            sound_engine.whimper()
            self._window.say(random.choice(loneliness), duration_ms=8000, sound="none")

    def on_notification(self, app: str, title: str, body: str, quiet: bool) -> None:
        if quiet or self._window._bubble:
            return
        short_body = (body[:70] + "…") if len(body) > 70 else body
        announce = f"📨 {app}: {title}"
        if short_body:
            announce += f"\n{short_body}"
        if self._slm.available:
            self._slm.ask(
                f"You just got a notification from {app}: '{title}'. "
                "Tell your owner about it in one short cute sentence.",
                on_done=self._window.say,
                track_history=False,
            )
        else:
            self._window.say(announce, duration_ms=7000)
