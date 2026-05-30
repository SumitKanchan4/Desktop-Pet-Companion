"""
ball_widget.py — A bouncy ball Buddy can chase and kick around the screen.

Physics: constant-energy bouncing off screen edges, velocity maintained
between kicks, slight energy loss on wall collisions.
No gravity — ball rolls around freely so Buddy can always chase it.
"""

from __future__ import annotations
import math
import random

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QColor, QRadialGradient, QBrush
from PyQt6.QtWidgets import QWidget

SIZE = 22   # ball diameter (px)

# Palette: panel of ball colours, pick one at spawn
_COLOURS = [
    (255,  80,  40),   # orange-red
    (40,  160, 255),   # sky blue
    (60,  200,  80),   # lime green
    (220,  60, 220),   # purple
    (255, 210,  30),   # golden yellow
]

_BOUNCE_ENERGY  = 0.78   # fraction of speed kept after wall bounce
_FRICTION       = 0.997  # per-frame air resistance (very light)
_MIN_SPEED      = 2.2    # never let ball stop completely
_STEP_MS        = 28     # physics tick ~36fps


class BallWidget(QWidget):
    """A self-animating bouncing ball."""

    def __init__(self, screen_rect, start_pos: QPoint) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.resize(SIZE, SIZE)

        self._screen = screen_rect

        # Floating-point position (top-left corner of widget)
        self._x = float(max(0, min(start_pos.x(), screen_rect.width()  - SIZE)))
        self._y = float(max(0, min(start_pos.y(), screen_rect.height() - SIZE)))

        # Random initial velocity
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(5.0, 7.5)
        self._vx = math.cos(angle) * speed
        self._vy = math.sin(angle) * speed

        # Colour for this ball
        r, g, b = random.choice(_COLOURS)
        self._col_main  = QColor(r, g, b)
        self._col_dark  = QColor(max(r - 80, 0), max(g - 80, 0), max(b - 80, 0))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(_STEP_MS)

        self.move(int(self._x), int(self._y))
        self.show()

    # ── Physics ──────────────────────────────────────────────────────────

    def _step(self) -> None:
        sw = self._screen.width()
        sh = self._screen.height()

        # Apply friction
        self._vx *= _FRICTION
        self._vy *= _FRICTION

        # Maintain minimum speed so ball never fully stops
        speed = math.hypot(self._vx, self._vy)
        if speed < _MIN_SPEED and speed > 0:
            scale = _MIN_SPEED / speed
            self._vx *= scale
            self._vy *= scale
        elif speed == 0:
            self._vx = _MIN_SPEED
            self._vy = 0.0

        self._x += self._vx
        self._y += self._vy

        # Bounce off left/right walls
        if self._x < 0:
            self._x = 0
            self._vx = abs(self._vx) * _BOUNCE_ENERGY
        elif self._x + SIZE > sw:
            self._x = sw - SIZE
            self._vx = -abs(self._vx) * _BOUNCE_ENERGY

        # Bounce off top/bottom walls
        if self._y < 0:
            self._y = 0
            self._vy = abs(self._vy) * _BOUNCE_ENERGY
        elif self._y + SIZE > sh:
            self._y = sh - SIZE
            self._vy = -abs(self._vy) * _BOUNCE_ENERGY

        self.move(int(self._x), int(self._y))
        self.update()

    # ── Public API ───────────────────────────────────────────────────────

    def kick(self, pet_cx: float, pet_cy: float) -> None:
        """Called when Buddy reaches the ball — sends it flying away."""
        ball_cx = self._x + SIZE / 2
        ball_cy = self._y + SIZE / 2
        dx = ball_cx - pet_cx
        dy = ball_cy - pet_cy
        dist = math.hypot(dx, dy) or 1.0
        speed = random.uniform(10.0, 16.0)
        self._vx = (dx / dist) * speed
        self._vy = (dy / dist) * speed - random.uniform(1, 3)  # slight upward

    def centre(self) -> QPoint:
        return QPoint(int(self._x + SIZE / 2), int(self._y + SIZE / 2))

    def vanish(self) -> None:
        self._timer.stop()
        self.hide()
        self.deleteLater()

    # ── Paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 3-D sphere gradient
        grad = QRadialGradient(SIZE * 0.35, SIZE * 0.30, SIZE * 0.65)
        grad.setColorAt(0.0, QColor(255, 255, 255, 180))
        grad.setColorAt(0.3, self._col_main)
        grad.setColorAt(1.0, self._col_dark)

        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, SIZE - 2, SIZE - 2)

        # Small specular highlight
        p.setBrush(QColor(255, 255, 255, 100))
        p.drawEllipse(SIZE // 4, SIZE // 5, SIZE // 4, SIZE // 5)

        p.end()
