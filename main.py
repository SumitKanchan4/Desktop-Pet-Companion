"""
main.py — Desktop Pet entry point.

Boot order:
  1. Load config.yaml
  2. Generate sprites if missing
  3. Start Qt application
  4. Instantiate core components + skills
  5. Wire signals and start periodic timers
"""

from __future__ import annotations
import os
import sys
import random
from pathlib import Path

# Force software OpenGL — prevents UpdateLayeredWindowIndirect errors on AMD iGPU
os.environ.setdefault("QT_OPENGL", "software")

import ctypes
import yaml
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout

# ── Single-instance lock via Windows named mutex ──────────────────────────────
_MUTEX_NAME = "DesktopPet_Buddy_SingleInstance"
_mutex = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)  # another instance is running — exit silently
# ─────────────────────────────────────────────────────────────────────────────

from sprite_gen import generate_all
from system.throttle import ResourceMonitor
from system.context_detector import ContextDetector
from system.notification_watcher import NotificationWatcher
from pet.brain import PetBrain
from pet.window import PetWindow
from intelligence.slm_client import SLMClient
from intelligence import weather as _weather_mod
from ui.tray import TrayManager
from pet.mood import MoodTracker

from skills.weather_skill import WeatherSkill
from skills.vision_skill import VisionSkill
from skills.play_skill import PlaySkill
from skills.social_skill import SocialSkill
from skills.commentary_skill import CommentarySkill
from skills.chain_skill import ChainSkill
from system.paths import CONFIG_PATH, CONFIG_EXAMPLE_PATH as EXAMPLE_PATH, SPRITES_DIR


def load_config() -> dict:
    # First-run: auto-copy the example so the user has a working config.yaml
    if not CONFIG_PATH.exists():
        if EXAMPLE_PATH.exists():
            import shutil
            shutil.copy(EXAMPLE_PATH, CONFIG_PATH)
        else:
            raise FileNotFoundError(
                "config.yaml not found. Copy config.example.yaml to config.yaml "
                "and fill in your settings."
            )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


def ask_user_name() -> str:
    """Show a friendly first-run dialog asking for the owner's name."""
    dlg = QDialog()
    dlg.setWindowTitle("Hey there! 🐾")
    dlg.setWindowFlags(
        Qt.WindowType.Dialog |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.MSWindowsFixedSizeDialogHint
    )
    dlg.setFixedWidth(360)

    layout = QVBoxLayout(dlg)
    layout.setSpacing(12)
    layout.setContentsMargins(20, 20, 20, 20)

    lbl = QLabel(
        "<b>Woof! I'm Buddy, your new desktop pet!</b><br><br>"
        "What should I call you? "
        "<small>(You can change this later in config.yaml)</small>"
    )
    lbl.setWordWrap(True)
    layout.addWidget(lbl)

    edit = QLineEdit()
    edit.setPlaceholderText("Enter your name…")
    edit.setMinimumHeight(32)
    layout.addWidget(edit)

    btns = QHBoxLayout()
    skip_btn = QPushButton("Skip")
    ok_btn   = QPushButton("Let's go! 🐾")
    ok_btn.setDefault(True)
    btns.addWidget(skip_btn)
    btns.addWidget(ok_btn)
    layout.addLayout(btns)

    ok_btn.clicked.connect(dlg.accept)
    skip_btn.clicked.connect(dlg.reject)
    edit.returnPressed.connect(dlg.accept)

    dlg.exec()
    return edit.text().strip()


def ensure_sprites() -> None:
    if not SPRITES_DIR.exists() or not list(SPRITES_DIR.glob("*.png")):
        print("Generating placeholder sprites...")
        generate_all()


# ---------------------------------------------------------------------------

class PetApp:
    def __init__(self, cfg: dict) -> None:
        self._cfg      = cfg
        self._username = cfg.get("user", {}).get("name", "") or "friend"

        # ── Core components ───────────────────────────────────────────────────
        self._brain   = PetBrain()
        self._monitor = ResourceMonitor(cfg)
        self._ctx     = ContextDetector(cfg)
        self._mood    = MoodTracker()
        self._slm     = SLMClient(cfg, username=self._username)
        self._window  = PetWindow(cfg, self._brain)
        self._tray    = TrayManager()
        self._notif   = NotificationWatcher()

        # ── Skills ────────────────────────────────────────────────────────────
        self._weather = WeatherSkill(self._window, self._slm)
        self._vision  = VisionSkill(cfg, self._window)
        self._play    = PlaySkill(self._window, self._brain, self._mood, cfg, self._username)
        self._social  = SocialSkill(self._window, self._slm, self._mood, self._username)
        self._comment = CommentarySkill(
            self._window, self._slm, self._brain,
            self._ctx, self._monitor, cfg, self._username,
        )
        self._chain   = ChainSkill(self._window, self._tray, cfg)

        self._wire_signals()
        self._start_periodic_timers()

    def _wire_signals(self) -> None:
        # Throttle → brain + window
        self._monitor.level_changed.connect(self._brain.on_throttle_changed)
        self._monitor.level_changed.connect(self._window.on_throttle_changed)

        # Context → brain + commentary skill
        self._ctx.context_changed.connect(self._brain.on_context_changed)
        self._ctx.context_changed.connect(self._comment.on_context_changed)

        # Window events
        self._window.double_clicked.connect(self._on_pet_clicked)
        self._window.treat_reached.connect(self._play.on_treat_reached)
        self._window.petted.connect(self._social.on_petted)

        # Mood shifts
        self._mood.mood_changed.connect(self._social.on_mood_changed)

        # Tray actions
        self._tray.quit_requested.connect(QApplication.quit)
        self._tray.hide_requested.connect(self._window.hide)
        self._tray.show_requested.connect(self._window.show)
        self._tray.speed_changed.connect(self._on_speed_change)
        self._tray.treat_requested.connect(self._play.on_give_treat)
        self._tray.fetch_requested.connect(self._play.on_play_fetch)
        self._tray.ball_requested.connect(self._play.on_spawn_ball)
        self._tray.vision_requested.connect(self._vision.do_peek)
        self._tray.chain_toggled.connect(self._chain.on_chain_toggled)

        # Notifications
        self._notif.new_notification.connect(
            lambda app, title, body: self._social.on_notification(app, title, body, self._comment.quiet)
        )

    def _start_periodic_timers(self) -> None:
        # Brain state tick (wander decisions)
        self._brain_timer = QTimer()
        self._brain_timer.timeout.connect(self._brain.tick)
        self._brain_timer.start(4000)

        # Periodic SLM context commentary
        comment_interval = int(
            self._cfg.get("slm", {}).get("behavior_update_interval_s", 300) * 1000
        )
        self._comment_timer = QTimer()
        self._comment_timer.timeout.connect(self._comment.maybe_comment)
        self._comment_timer.start(comment_interval)

        # Break reminder check every minute
        self._break_timer = QTimer()
        self._break_timer.timeout.connect(self._comment.check_break)
        self._break_timer.start(60_000)

        # Ball chase target refresh every 80 ms
        self._ball_timer = QTimer()
        self._ball_timer.timeout.connect(self._play.ball_track_step)
        self._ball_timer.start(80)

        # Idle behaviours every 90 s
        self._idle_timer = QTimer()
        self._idle_timer.timeout.connect(
            lambda: self._comment.do_idle_behavior(self._play.active_treat is not None)
        )
        self._idle_timer.start(90_000)

        # Cursor following check every 25 s
        self._cursor_timer = QTimer()
        self._cursor_timer.timeout.connect(
            lambda: self._comment.maybe_follow_cursor(self._play.active_treat is not None)
        )
        self._cursor_timer.start(25_000)

        # Screen vision auto-peek every 15 min
        self._vision_timer = QTimer()
        self._vision_timer.timeout.connect(
            lambda: self._vision.auto_peek(
                self._comment.quiet,
                bool(self._window._bubble or self._play.active_treat or self._play.active_ball),
            )
        )
        self._vision_timer.start(15 * 60 * 1000)

        # Weather fetch: first after 10 s, then every hour
        QTimer.singleShot(10_000, lambda: _weather_mod.fetch(self._weather.background_cb))
        self._weather_timer = QTimer()
        self._weather_timer.timeout.connect(
            lambda: _weather_mod.fetch(self._weather.background_cb)
        )
        self._weather_timer.start(60 * 60 * 1000)

        # Startup greeting after 2 s
        QTimer.singleShot(2000, lambda: self._comment.greet(self._weather.data))

    def show(self) -> None:
        self._window.show()
        self._monitor.start()
        self._ctx.start()

    # ── Remaining app-level handlers ──────────────────────────────────────────

    def _on_pet_clicked(self, user_text: str) -> None:
        self._mood.on_interacted()
        prompt = (
            f"The user said to you: \"{user_text}\". Respond in character."
            if user_text else
            "The user just double-clicked and poked you. React cutely."
        )

        def _fallback(err: str = "") -> None:
            self._window.say(random.choice(["Woof! 🐾", "Bork bork!", "*wags tail furiously*", "Pat me more!"]))

        if self._slm.available:
            self._slm.ask(prompt, on_done=self._window.say, on_error=_fallback)
        else:
            _fallback()

    def _on_speed_change(self, multiplier: float) -> None:
        base = self._cfg.get("pet", {}).get("speed", 2.0)
        self._window._base_speed = base * multiplier


# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    cfg = load_config()
    ensure_sprites()

    # First-run: ask owner's name if not yet set
    if not cfg.get("user", {}).get("name", ""):
        name = ask_user_name()
        if name:
            cfg.setdefault("user", {})["name"] = name
            save_config(cfg)

    pet = PetApp(cfg)
    pet.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
