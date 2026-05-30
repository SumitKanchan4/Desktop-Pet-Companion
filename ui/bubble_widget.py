"""
bubble_widget.py — Floating speech-bubble overlay widget for Buddy.

Replaces the old painted-on SpeechBubble approach in pet/window.py.
This is a real QWidget so it gets:
  • Drop shadow via QGraphicsDropShadowEffect
  • Smooth slide-in / fade-out animations using QPropertyAnimation
  • Proper font anti-aliasing (no hand-painting hacks)
  • Two visual modes: "buddy" (warm cream, paw icon) / "system" (blue-grey)

Usage
-----
    bubble = BubbleWidget(parent_window)
    bubble.show_text("Woof! It's raining outside 🌧️")
    bubble.show_text("Model not loaded yet.", mode="system")
"""

from __future__ import annotations

import math
from typing import Literal

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSequentialAnimationGroup,
    QTimer,
    Qt,
    pyqtProperty,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
)
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
)
from ui.fonts import FONT_FAMILY_UI

BubbleMode = Literal["buddy", "system"]

# ── Palette ───────────────────────────────────────────────────────────────────
_BUDDY_BG      = QColor(255, 252, 230)   # warm cream
_BUDDY_BORDER  = QColor(200, 160, 60, 180)
_BUDDY_TEXT    = QColor(45, 30, 10)
_SYSTEM_BG     = QColor(40, 44, 52, 220)  # dark pill
_SYSTEM_BORDER = QColor(80, 120, 200, 160)
_SYSTEM_TEXT   = QColor(200, 215, 255)

_FONT_FAMILY = FONT_FAMILY_UI   # Nunito (bundled) → Segoe UI Variable → Segoe UI
_FONT_SIZE   = 11               # pt — clearly legible without being huge
_MAX_WIDTH   = 280      # px before wrapping
_PAD_H       = 14       # horizontal padding
_PAD_V       = 10       # vertical padding
_TAIL_H      = 10       # height of the pointy tail
_CORNER_R    = 14       # rounded corner radius
_ICON_TEXT   = "🐾 "   # prepended in buddy mode


class BubbleWidget(QWidget):
    """
    A frameless, translucent, always-on-top speech bubble.

    The widget positions itself above ``anchor_widget`` (the pet window).
    Call ``show_text(text)`` to display a new message.
    The bubble auto-dismisses after ``duration_ms`` and can be hovered to
    pause the countdown.
    """

    def __init__(self, anchor_widget: QWidget) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                              Qt.WindowType.WindowStaysOnTopHint |
                              Qt.WindowType.Tool)
        self._anchor = anchor_widget
        self._text   = ""
        self._lines: list[str] = []
        self._mode: BubbleMode = "buddy"
        self._alpha  = 0.0          # driven by animation (0.0 – 1.0)
        self._y_off  = 0.0          # slide-in offset in px (driven by animation)
        self._duration_ms = 8000
        self._hovered = False

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        # Dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._start_fade_out)

        # Animation group: slide-in + (after pause) fade-out
        self._anim_in_y    = QPropertyAnimation(self, b"yOff")
        self._anim_in_a    = QPropertyAnimation(self, b"bubbleAlpha")
        self._anim_out_a   = QPropertyAnimation(self, b"bubbleAlpha")

        for a in (self._anim_in_y, self._anim_in_a, self._anim_out_a):
            a.setDuration(180)

        self._anim_in_y.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_out_a.setEasingCurve(QEasingCurve.Type.InQuad)
        self._anim_out_a.finished.connect(self.hide)

    # ── Qt property accessors (required for QPropertyAnimation) ──────────────

    def _get_alpha(self) -> float:
        return self._alpha

    def _set_alpha(self, v: float) -> None:
        self._alpha = max(0.0, min(1.0, v))
        self.update()

    bubbleAlpha = pyqtProperty(float, _get_alpha, _set_alpha)

    def _get_y_off(self) -> float:
        return self._y_off

    def _set_y_off(self, v: float) -> None:
        self._y_off = v
        self._reposition()
        self.update()

    yOff = pyqtProperty(float, _get_y_off, _set_y_off)

    # ── Public API ────────────────────────────────────────────────────────────

    def show_text(self, text: str, duration_ms: int = 8000,
                  mode: BubbleMode = "buddy") -> None:
        """Display ``text`` in the bubble. Cancels any previous message."""
        self._dismiss_timer.stop()
        self._anim_out_a.stop()

        self._text        = text
        self._mode        = mode
        self._duration_ms = duration_ms
        self._lines       = self._wrap(text, mode)

        self._resize_to_content()
        self._reposition()
        self.show()

        # Slide in from +12 px below and fade from 0 → 1
        self._anim_in_y.setStartValue(12.0)
        self._anim_in_y.setEndValue(0.0)
        self._anim_in_y.start()

        self._anim_in_a.setStartValue(0.0)
        self._anim_in_a.setEndValue(1.0)
        self._anim_in_a.start()

        self._dismiss_timer.start(duration_ms)

    def dismiss(self) -> None:
        """Force-dismiss without waiting for the timer."""
        self._dismiss_timer.stop()
        self._start_fade_out()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _wrap(self, text: str, mode: BubbleMode) -> list[str]:
        """Word-wrap text into lines that fit within _MAX_WIDTH."""
        prefix = _ICON_TEXT if mode == "buddy" else ""
        font = QFont(_FONT_FAMILY, _FONT_SIZE)
        fm   = QFontMetrics(font)
        avail = _MAX_WIDTH - _PAD_H * 2

        # Split on explicit newlines first
        paragraphs = (prefix + text).split("\n")
        lines: list[str] = []
        for para in paragraphs:
            words = para.split()
            line  = ""
            for w in words:
                test = (line + " " + w).strip()
                if fm.horizontalAdvance(test) > avail:
                    if line:
                        lines.append(line)
                    line = w
                else:
                    line = test
            if line:
                lines.append(line)
        return lines or [""]

    def _resize_to_content(self) -> None:
        font = QFont(_FONT_FAMILY, _FONT_SIZE)
        fm   = QFontMetrics(font)
        line_h = fm.height() + 3

        content_w = max(fm.horizontalAdvance(l) for l in self._lines)
        content_h = line_h * len(self._lines)

        w = content_w + _PAD_H * 2
        h = content_h + _PAD_V * 2 + _TAIL_H  # extra for tail
        self.resize(w, h)

    def _reposition(self) -> None:
        """Place the bubble above the anchor pet window."""
        if not self._anchor.isVisible():
            return
        anchor_g = self._anchor.geometry()  # global pos + size
        screen   = (QApplication.primaryScreen().geometry()
                    if QApplication.primaryScreen() else QRect(0, 0, 1920, 1080))

        bw, bh = self.width(), self.height()

        # Horizontally centre over pet
        cx = anchor_g.center().x()
        x  = cx - bw // 2
        x  = max(8, min(x, screen.width() - bw - 8))

        # Vertically above pet, shifted by live y_off animation
        y = anchor_g.top() - bh - 6 + int(self._y_off)
        if y < 8:
            # Not enough space above — flip below instead
            y = anchor_g.bottom() + 6 + int(self._y_off)

        self.move(x, y)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        if not self._lines:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        alpha_i = int(self._alpha * 255)
        w, h    = self.width(), self.height()
        body_h  = h - _TAIL_H

        is_buddy = self._mode == "buddy"
        bg_col   = QColor(_BUDDY_BG)
        brd_col  = QColor(_BUDDY_BORDER)
        txt_col  = QColor(_BUDDY_TEXT)
        if not is_buddy:
            bg_col  = QColor(_SYSTEM_BG)
            brd_col = QColor(_SYSTEM_BORDER)
            txt_col = QColor(_SYSTEM_TEXT)

        bg_col.setAlpha(int(bg_col.alpha() / 255 * alpha_i))
        brd_col.setAlpha(int(brd_col.alpha() / 255 * alpha_i))
        txt_col.setAlpha(alpha_i)

        # ── Bubble body (rounded rect) ────────────────────────────────────────
        path = QPainterPath()
        rect = QRect(0, 0, w, body_h)
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(),
                            _CORNER_R, _CORNER_R)

        # ── Tail (downward-pointing triangle from bottom centre) ──────────────
        mid = w // 2
        path.moveTo(mid - 8, body_h)
        path.lineTo(mid,     body_h + _TAIL_H)
        path.lineTo(mid + 8, body_h)
        path.closeSubpath()

        painter.setPen(QPen(brd_col, 2.0))
        painter.setBrush(QBrush(bg_col))
        painter.drawPath(path)

        # ── Text ──────────────────────────────────────────────────────────────
        font = QFont(_FONT_FAMILY, _FONT_SIZE)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(txt_col)

        fm     = QFontMetrics(font)
        line_h = fm.height() + 3
        total_text_h = line_h * len(self._lines)
        ty = (body_h - total_text_h) // 2 + fm.ascent()

        for i, line in enumerate(self._lines):
            painter.drawText(_PAD_H, ty + i * line_h, line)

        painter.end()

    # ── Mouse hover — pause dismiss timer ────────────────────────────────────

    def enterEvent(self, _event) -> None:
        self._hovered = True
        self._dismiss_timer.stop()

    def leaveEvent(self, _event) -> None:
        self._hovered = False
        # Resume with reduced remaining time so it doesn't linger forever
        remaining = max(1500, self._dismiss_timer.remainingTime()
                        if self._dismiss_timer.isActive() else 1500)
        self._dismiss_timer.start(remaining)

    # ── Fade-out ──────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _start_fade_out(self) -> None:
        self._anim_out_a.setStartValue(self._alpha)
        self._anim_out_a.setEndValue(0.0)
        self._anim_out_a.setDuration(350)
        self._anim_out_a.start()
