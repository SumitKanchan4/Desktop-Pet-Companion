"""
tray.py — System tray icon with context menu for controlling the pet.
"""

from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu


def _make_tray_icon() -> QIcon:
    """Creates a simple coloured paw icon if no icon file exists."""
    from system.paths import TRAY_ICON_PATH
    icon_path = TRAY_ICON_PATH
    if icon_path.exists():
        return QIcon(str(icon_path))
    px = QPixmap(32, 32)
    px.fill(QColor(210, 160, 80))
    return QIcon(px)


class TrayManager(QObject):
    """Manages the system tray icon and menu actions."""

    quit_requested   = pyqtSignal()
    hide_requested   = pyqtSignal()
    show_requested   = pyqtSignal()
    speed_changed    = pyqtSignal(float)   # multiplier
    size_changed     = pyqtSignal(int)     # scale factor
    treat_requested  = pyqtSignal()        # give Buddy a treat
    fetch_requested  = pyqtSignal()        # play fetch
    ball_requested   = pyqtSignal()        # spawn a ball to play with
    vision_requested = pyqtSignal()        # ask Buddy what he sees on screen
    chain_toggled    = pyqtSignal()        # toggle chain on/off
    settings_requested = pyqtSignal()      # open the Settings dialog
    about_requested    = pyqtSignal()      # open the About dialog

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tray = QSystemTrayIcon(_make_tray_icon(), parent)
        self._tray.setToolTip("Desktop Pet — Buddy 🐾")
        self._build_menu()
        self._tray.show()

    def _build_menu(self) -> None:
        menu = QMenu()

        menu.addAction("Show Buddy",  self.show_requested.emit)
        menu.addAction("Hide Buddy",  self.hide_requested.emit)
        menu.addSeparator()

        speed_menu = menu.addMenu("Speed")
        speed_menu.addAction("Slow",   lambda: self.speed_changed.emit(0.5))
        speed_menu.addAction("Normal", lambda: self.speed_changed.emit(1.0))
        speed_menu.addAction("Fast",   lambda: self.speed_changed.emit(2.0))

        size_menu = menu.addMenu("Size")
        size_menu.addAction("Small",  lambda: self.size_changed.emit(2))
        size_menu.addAction("Normal", lambda: self.size_changed.emit(3))
        size_menu.addAction("Large",  lambda: self.size_changed.emit(4))

        menu.addSeparator()

        menu.addAction("🍖  Give Treat",  self.treat_requested.emit)
        menu.addAction("🎾  Play Fetch",  self.fetch_requested.emit)
        menu.addAction("🎱  Ball Time",   self.ball_requested.emit)
        menu.addAction("👁️  What do you see?", self.vision_requested.emit)
        menu.addSeparator()
        self._chain_action = menu.addAction("⛓️  Chain here", self.chain_toggled.emit)

        menu.addSeparator()
        menu.addAction("⚙️  Settings…", self.settings_requested.emit)
        menu.addAction("ℹ️  About…",    self.about_requested.emit)
        menu.addAction("Quit", self.quit_requested.emit)

        self._tray.setContextMenu(menu)

    def set_chain_text(self, text: str) -> None:
        """Update the chain menu item label to reflect current state."""
        self._chain_action.setText(text)

    def notify(self, title: str, message: str, duration_ms: int = 3000) -> None:
        self._tray.showMessage(title, message,
                               QSystemTrayIcon.MessageIcon.Information,
                               duration_ms)
