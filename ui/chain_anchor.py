"""
chain_anchor.py — A draggable stake widget that anchors Buddy's movement radius.

When placed on screen, Buddy cannot wander beyond `chain_radius` pixels from
the anchor centre. Drag the stake to reposition the allowed zone.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPen, QBrush
from PyQt6.QtWidgets import QWidget

SIZE = 30   # widget width & height in pixels


class ChainAnchor(QWidget):
    """A small draggable stake icon pinned to the screen."""

    moved = pyqtSignal(QPoint)   # emits new centre when dragged

    def __init__(self, screen_pos: QPoint, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFixedSize(SIZE, SIZE)
        self.setToolTip("Buddy's chain anchor — drag to reposition")
        self._drag_offset = QPoint()
        # Centre the widget on the requested screen point
        self.move(screen_pos - QPoint(SIZE // 2, SIZE // 2))
        self.show()

    # ── Public API ────────────────────────────────────────────────────

    def centre(self) -> QPoint:
        """Return the anchor's centre in screen coordinates."""
        return self.pos() + QPoint(SIZE // 2, SIZE // 2)

    def vanish(self) -> None:
        self.hide()
        self.deleteLater()

    # ── Paint ─────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = SIZE // 2

        # Ground shadow
        p.setBrush(QColor(0, 0, 0, 45))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - 7, SIZE - 7, 14, 5)

        # Stake body (wood brown rectangle)
        stake_w, stake_h = 7, 16
        sx = cx - stake_w // 2
        sy = SIZE // 2 - 2
        p.setBrush(QColor(165, 105, 48))
        p.setPen(QPen(QColor(105, 62, 20), 1))
        p.drawRoundedRect(sx, sy, stake_w, stake_h, 2, 2)

        # Wood grain lines
        p.setPen(QPen(QColor(130, 78, 30), 1))
        p.drawLine(sx + 2, sy + 3, sx + 2, sy + stake_h - 4)
        p.drawLine(sx + 5, sy + 2, sx + 5, sy + stake_h - 3)

        # Pointed tip
        tip = QPainterPath()
        tip.moveTo(sx,              sy + stake_h - 1)
        tip.lineTo(sx + stake_w,    sy + stake_h - 1)
        tip.lineTo(cx,              SIZE - 1)
        tip.closeSubpath()
        p.setBrush(QColor(130, 78, 30))
        p.setPen(QPen(QColor(90, 50, 15), 1))
        p.drawPath(tip)

        # Metal ring at top
        ring_r = 6
        ring_x = cx - ring_r
        ring_y = SIZE // 2 - stake_h // 2 - ring_r + 2
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(170, 170, 185), 2.5))
        p.drawEllipse(ring_x, ring_y, ring_r * 2, ring_r * 2)

        # Ring shine
        p.setPen(QPen(QColor(220, 220, 235), 1.2))
        p.drawArc(ring_x + 1, ring_y + 1, ring_r * 2 - 2, ring_r * 2 - 2, 60 * 16, 120 * 16)

        p.end()

    # ── Drag ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.pos()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(self.mapToGlobal(event.pos()) - self._drag_offset)
            self.moved.emit(self.centre())
