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
from ui.settings_dialog import SettingsDialog
from ui.fonts import load_app_fonts
from system.version import APP_VERSION, GITHUB_REPO
from system.updater import UpdateChecker
import system.autostart as _autostart


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
    # Only treat as a real answer if user explicitly accepted (Enter or "Let's go!")
    if dlg.result() == QDialog.DialogCode.Accepted:
        return edit.text().strip()
    return ""


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

        # Window events — double_clicked now only fires for non-chat-bar usage
        self._window.double_clicked.connect(self._on_pet_clicked)
        self._window.treat_reached.connect(self._play.on_treat_reached)
        self._window.petted.connect(self._social.on_petted)

        # Chat bar — floating input widget
        self._window._chat_bar.message_sent.connect(self._on_chat_message)

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
        self._tray.settings_requested.connect(self._open_settings)
        self._tray.about_requested.connect(self._open_about)

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

        # Auto-update check (daemon thread, only if enabled in config)
        if self._cfg.get("app", {}).get("auto_update", True):
            self._updater = UpdateChecker()
            self._updater.download_started.connect(self._on_update_download_started)
            self._updater.download_complete.connect(self._on_update_ready)
            self._updater.download_failed.connect(self._on_update_failed)
            self._updater.start()

    def show(self) -> None:
        self._window.show()
        self._monitor.start()
        self._ctx.start()

    # ── Remaining app-level handlers ──────────────────────────────────────────

    def _on_pet_clicked(self, user_text: str) -> None:
        """Handles fallback double-click (empty emit or future use)."""
        if user_text:
            self._on_chat_message(user_text)
        else:
            self._mood.on_interacted()
            self._window.say(random.choice(["Woof! 🐾", "Bork bork!", "*wags tail furiously*", "Pat me more!"]))

    def _on_chat_message(self, user_text: str) -> None:
        """Handle a message from the chat bar."""
        self._mood.on_interacted()
        prompt = f'The user said to you: "{user_text}". Respond in character.'
        chat_bar = self._window._chat_bar

        def _on_reply(text: str) -> None:
            self._window.say(text)
            chat_bar.clear_typing()

        def _fallback(err: str = "") -> None:
            reply = random.choice(["Woof! 🐾", "Bork bork!", "*wags tail furiously*", "Pat me more!"])
            self._window.say(reply)
            chat_bar.clear_typing()

        if self._slm.available:
            self._slm.ask(prompt, on_done=_on_reply, on_error=_fallback)
        else:
            _fallback()

    def _on_speed_change(self, multiplier: float) -> None:
        base = self._cfg.get("pet", {}).get("speed", 2.0)
        self._window._base_speed = base * multiplier

    def _open_settings(self) -> None:
        """Show the Settings dialog and hot-apply what we can on save."""
        dlg = SettingsDialog(self._cfg)
        dlg.settings_saved.connect(self._apply_settings)
        dlg.exec()

    def _open_about(self) -> None:
        """Show a simple About dialog."""
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setWindowTitle("About Buddy")
        msg.setWindowFlags(
            msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        msg.setIconPixmap(
            msg.style().standardPixmap(
                msg.style().StandardPixmap.SP_MessageBoxInformation
            )
        )
        msg.setText(
            f"<b>Desktop Pet — Buddy 🐾</b><br>"
            f"Version {APP_VERSION}"
        )
        msg.setInformativeText(
            "A playful AI-powered desktop companion.<br><br>"
            f'<a href="https://github.com/{GITHUB_REPO}">github.com/{GITHUB_REPO}</a><br><br>'
            "© 2025 Sumit Kanchan &nbsp;|&nbsp; MIT License"
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.exec()

    def _on_update_download_started(self, version: str) -> None:
        """Called when the installer download begins."""
        self._window.say(f"Downloading update {version}… I'll let you know when it's ready! 📦")

    def _on_update_ready(self, version: str, installer_path: str) -> None:
        """Installer downloaded — ask user to install now or later."""
        from PyQt6.QtWidgets import QMessageBox, QPushButton
        self._tray.notify("Buddy — Update ready", f"Version {version} downloaded. Click to install.")

        msg = QMessageBox()
        msg.setWindowTitle("Buddy — Update Ready")
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        msg.setText(f"<b>Version {version} is ready to install.</b>")
        msg.setInformativeText(
            "Buddy will close and the installer will launch.\n"
            "Your settings and config are kept."
        )
        install_btn = msg.addButton("Install now", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if msg.clickedButton() is install_btn:
            UpdateChecker.launch_installer(installer_path)

    def _on_update_failed(self, version: str, reason: str) -> None:
        """Download failed — log quietly, no user-facing noise."""
        print(f"[updater] download failed for v{version}: {reason}")

    def _apply_settings(self, cfg: dict) -> None:
        """Persist updated config and propagate hot-applicable changes."""
        save_config(cfg)
        # Hot-apply: SLM model / enabled / username
        slm_cfg = cfg.get("slm", {})
        self._slm.set_enabled(slm_cfg.get("backend", "ollama") != "disabled")
        self._slm.set_model(slm_cfg.get("text_model", ""))
        new_name = cfg.get("user", {}).get("name", "") or "friend"
        self._username = new_name
        self._slm.set_username(new_name)
        self._tray.notify("Buddy", "Settings saved. Some changes apply on next restart.")


# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    load_app_fonts()  # register Nunito (if TTFs present) before any widget creation

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
