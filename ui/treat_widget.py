"""
treat_widget.py — A floating bone that Buddy can chase.

Used by both:
  • Give Treat  — bone appears near Buddy, Buddy runs to it immediately.
  • Play Fetch  — bone is "thrown" (animated slide across screen),
                  Buddy chases it after it lands.
"""

from __future__ import annotations
import io
import random

from PIL import Image, ImageDraw

from PyQt6.QtCore import (
    Qt, QPoint, QTimer, QPropertyAnimation,
    QEasingCurve, pyqtSignal, QByteArray,
)
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget, QApplication


# ── Bone sprite ────────────────────────────────────────────────────────────────

def _make_bone_pixmap(size: int = 32) -> QPixmap:
    """Draw a simple bone using Pillow, return as QPixmap."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    c   = (242, 224, 180, 255)   # ivory bone
    ol  = (165, 120,  65, 255)   # outline

    mid_y = size // 2
    # Shaft
    d.rectangle([size // 4, mid_y - 3, size * 3 // 4, mid_y + 3],
                fill=c, outline=ol)
    # Four knobs (two each end)
    for kx, ky in [
        (size // 4,     mid_y - 5), (size // 4,     mid_y + 5),
        (size * 3 // 4, mid_y - 5), (size * 3 // 4, mid_y + 5),
    ]:
        d.ellipse([kx - 5, ky - 5, kx + 5, ky + 5], fill=c, outline=ol)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    px = QPixmap()
    px.loadFromData(buf.read())
    return px


BONE_PX = None   # lazy singleton


def _bone_pixmap() -> QPixmap:
    global BONE_PX
    if BONE_PX is None:
        BONE_PX = _make_bone_pixmap(32)
    return BONE_PX


# ── Widget ─────────────────────────────────────────────────────────────────────

class TreatWidget(QWidget):
    """
    A small bone widget that floats on screen.

    Signals
    -------
    landed : emitted when the throw animation finishes (fetch mode).
             main.py then tells PetWindow to start chasing.
    """

    landed = pyqtSignal(QPoint)   # bone screen-centre when it stops

    SIZE = 32

    def __init__(self, start: QPoint, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(self.SIZE, self.SIZE)
        self.move(start)
        self.show()
        self._anim: QPropertyAnimation | None = None

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.drawPixmap(0, 0, _bone_pixmap())
        p.end()

    def centre(self) -> QPoint:
        return QPoint(self.x() + self.SIZE // 2, self.y() + self.SIZE // 2)

    def throw_to(self, target: QPoint, duration_ms: int = 900) -> None:
        """Animate bone flying from current position to target, then emit landed."""
        self._anim = QPropertyAnimation(self, QByteArray(b"pos"))
        self._anim.setDuration(duration_ms)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._anim.finished.connect(self._on_landed)
        self._anim.start()

    def _on_landed(self) -> None:
        self.landed.emit(self.centre())

    def vanish(self) -> None:
        """Fade out and delete."""
        self.hide()
        self.deleteLater()


# ── Factory helpers ────────────────────────────────────────────────────────────

def spawn_treat(pet_pos: QPoint, screen_rect) -> TreatWidget:
    """
    Drop a treat somewhere visible but not too far from Buddy —
    Buddy can run to it immediately.
    """
    margin = 60
    sx = max(margin, min(screen_rect.width()  - margin, pet_pos.x() + random.randint(-180, 180)))
    sy = max(margin, min(screen_rect.height() - margin, pet_pos.y() + random.randint(-100, 100)))
    return TreatWidget(QPoint(sx - TreatWidget.SIZE // 2,
                              sy - TreatWidget.SIZE // 2))


def spawn_fetch(pet_pos: QPoint, screen_rect) -> tuple[TreatWidget, QPoint]:
    """
    Throw bone from Buddy's position to a random far spot.
    Returns (widget, landing_pos_topleft) — widget.throw_to() is called
    by the caller after connecting to widget.landed.
    """
    margin = 80
    attempts = 0
    while True:
        lx = random.randint(margin, screen_rect.width()  - margin)
        ly = random.randint(margin, screen_rect.height() - margin)
        dist = ((lx - pet_pos.x()) ** 2 + (ly - pet_pos.y()) ** 2) ** 0.5
        if dist > 250 or attempts > 10:
            break
        attempts += 1

    landing = QPoint(lx - TreatWidget.SIZE // 2, ly - TreatWidget.SIZE // 2)
    widget  = TreatWidget(pet_pos)
    return widget, landing
