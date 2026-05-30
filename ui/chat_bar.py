"""
chat_bar.py — Floating chat input bar for talking to Buddy.

Replaces the old QInputDialog popup.  This is a persistent frameless widget
that slides up from just above the pet, stays open for a conversation, and
auto-hides after a configurable idle period.

Signals
-------
message_sent(str)   — emitted when the user submits a message
dismissed()         — emitted when the bar closes (Esc or idle timeout)

Usage
-----
    bar = ChatBar(parent=None)
    bar.anchor_to(pet_window)
    bar.message_sent.connect(on_message)
    bar.popup()            # open on double-click
    bar.show_typing()      # while Buddy is "thinking"
    bar.clear_typing()     # when response arrives
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QLinearGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)
from ui.fonts import FONT_FAMILY_UI


# ── Design tokens ─────────────────────────────────────────────────────────────
_BAR_H         = 48           # total bar height px
_BAR_MIN_W     = 320
_BAR_MAX_W     = 440
_CORNER_R      = 24           # fully pill-shaped
_BG_NORMAL     = QColor(28, 28, 32, 235)
_BG_FOCUSED    = QColor(32, 34, 42, 250)
_BORDER_IDLE   = QColor(80, 80, 100, 120)
_BORDER_FOCUS  = QColor(130, 160, 255, 200)
_TEXT_COLOR    = QColor(230, 230, 240)
_HINT_COLOR    = QColor(130, 130, 160)
_SEND_NORMAL   = QColor(100, 130, 255)
_SEND_HOVER    = QColor(130, 160, 255)
_TYPING_DOT    = QColor(160, 170, 200)

# How long to wait with no input before auto-closing (ms)
_IDLE_TIMEOUT  = 20_000


class _TypingDots(QWidget):
    """Three animated dots shown while Buddy is processing a reply."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(32, 20)
        self.hide()

    def start(self) -> None:
        self._phase = 0
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    @pyqtSlot()
    def _tick(self) -> None:
        self._phase = (self._phase + 1) % 4
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = 4
        for i in range(3):
            lit = (self._phase - 1) % 4 == i or self._phase == 3
            col = QColor(_TYPING_DOT)
            col.setAlpha(240 if lit else 100)
            painter.setBrush(QBrush(col))
            painter.setPen(Qt.PenStyle.NoPen)
            cx = 4 + i * 12
            cy = self.height() // 2
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        painter.end()


class _StyledLineEdit(QLineEdit):
    """Transparent QLineEdit — background drawn by parent ChatBar."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "QLineEdit {"
            "  background: transparent;"
            "  border: none;"
            f" color: rgba({_TEXT_COLOR.red()},{_TEXT_COLOR.green()},{_TEXT_COLOR.blue()},240);"
            f" font-family: '{FONT_FAMILY_UI}'; font-size: 12pt;"
            "  selection-background-color: rgba(100,140,255,120);"
            "}"
        )
        self.setPlaceholderText("Say something to Buddy…")
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        # Style placeholder colour
        style = self.styleSheet() + (
            "QLineEdit::placeholder {"
            f" color: rgba({_HINT_COLOR.red()},{_HINT_COLOR.green()},{_HINT_COLOR.blue()},160);"
            "}"
        )
        self.setStyleSheet(style)


class ChatBar(QWidget):
    """
    Pill-shaped floating chat bar.  Anchored above the pet window.
    """

    message_sent = pyqtSignal(str)
    dismissed    = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint |
                                Qt.WindowType.WindowStaysOnTopHint |
                                Qt.WindowType.Tool)
        self._anchor: QWidget | None = None
        self._focused = False
        self._alpha   = 0.0          # 0–1, animated
        self._drag_pos: QPoint | None = None   # set while dragging the bar
        self._user_moved = False               # True once the user drags it

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFixedHeight(_BAR_H)
        self.setMinimumWidth(_BAR_MIN_W)
        self.setMaximumWidth(_BAR_MAX_W)


        # ── Layout ────────────────────────────────────────────────────────────
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(18, 0, 10, 0)
        self._layout.setSpacing(8)

        self._dots = _TypingDots(self)

        self._input = _StyledLineEdit(self)
        self._input.returnPressed.connect(self._on_send)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.installEventFilter(self)

        self._send_btn = QPushButton("➤", self)
        self._send_btn.setFixedSize(32, 32)
        self._send_btn.setToolTip("Send (Enter)")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.clicked.connect(self._on_send)
        self._send_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: rgba({_SEND_NORMAL.red()},{_SEND_NORMAL.green()},{_SEND_NORMAL.blue()},200);"
            f"  color: white; border-radius: 16px;"
            f"  font-size: 14px; font-family: '{FONT_FAMILY_UI}';"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: rgba({_SEND_HOVER.red()},{_SEND_HOVER.green()},{_SEND_HOVER.blue()},230);"
            f"}}"
        )

        self._layout.addWidget(self._dots, 0)
        self._layout.addWidget(self._input, 1)
        self._layout.addWidget(self._send_btn, 0)

        # ── Idle auto-close timer ─────────────────────────────────────────────
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._close_anim)

        # ── Slide animation ───────────────────────────────────────────────────
        self._anim = QPropertyAnimation(self, b"barAlpha")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_done)
        self._closing = False

    # ── Qt property ──────────────────────────────────────────────────────────

    def _get_alpha(self) -> float:
        return self._alpha

    def _set_alpha(self, v: float) -> None:
        self._alpha = max(0.0, min(1.0, v))
        self.setWindowOpacity(self._alpha)
        self.update()

    barAlpha = pyqtProperty(float, _get_alpha, _set_alpha)

    # ── Public API ────────────────────────────────────────────────────────────

    def anchor_to(self, widget: QWidget) -> None:
        """Set the widget above which the bar positions itself."""
        self._anchor = widget

    def popup(self) -> None:
        """Show the bar and focus the input.  Call on every double-click."""
        self._closing = False
        # Only auto-reposition if the user hasn't dragged it somewhere
        if not self._user_moved:
            self._reposition()
        self.show()
        self.raise_()

        self._anim.stop()
        self._anim.setStartValue(self._alpha)
        self._anim.setEndValue(1.0)
        self._anim.start()

        self._idle_timer.start(_IDLE_TIMEOUT)
        # Give Qt a tick to show the widget before focusing
        QTimer.singleShot(50, self._focus_input)

    def show_typing(self) -> None:
        """Display animated typing dots — call while waiting for SLM."""
        self._input.setEnabled(False)
        self._input.setPlaceholderText("Buddy is thinking…")
        self._dots.start()
        # Keep bar visible during inference
        self._idle_timer.stop()

    def clear_typing(self) -> None:
        """Re-enable input after SLM response arrives."""
        self._dots.stop()
        self._input.setEnabled(True)
        self._input.setPlaceholderText("Say something to Buddy…")
        self._idle_timer.start(_IDLE_TIMEOUT)

    # ── Internals ────────────────────────────────────────────────────────────

    def _focus_input(self) -> None:
        self._input.setFocus(Qt.FocusReason.OtherFocusReason)
        self.activateWindow()

    def _reposition(self) -> None:
        if not self._anchor:
            return
        screen = (QApplication.primaryScreen().geometry()
                  if QApplication.primaryScreen() else QRect(0, 0, 1920, 1080))
        anchor_g = self._anchor.geometry()

        # Width: clamp to screen, prefer BAR_MAX_W
        bw = min(_BAR_MAX_W, screen.width() - 40)
        self.setFixedWidth(bw)

        cx = anchor_g.center().x()
        x  = max(20, min(cx - bw // 2, screen.width() - bw - 20))
        y  = anchor_g.top() - _BAR_H - 8

        # If too close to top, put below pet instead
        if y < 20:
            y = anchor_g.bottom() + 8

        self.move(x, y)

    @pyqtSlot()
    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.message_sent.emit(text)
        self.show_typing()
        # Don't close — wait for clear_typing() then idle timeout

    @pyqtSlot()
    def _on_text_changed(self) -> None:
        # Reset idle timer every keystroke
        self._idle_timer.start(_IDLE_TIMEOUT)

    def _close_anim(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._anim.stop()
        self._anim.setStartValue(self._alpha)
        self._anim.setEndValue(0.0)
        self._anim.start()

    @pyqtSlot()
    def _on_anim_done(self) -> None:
        if self._closing:
            self.hide()
            self._input.clear()
            self._dots.stop()
            self._input.setEnabled(True)
            self._input.setPlaceholderText("Say something to Buddy…")
            self.dismissed.emit()
    # ── Drag to reposition ──────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Only drag from the bar background, not from the input or button
            if not self._input.geometry().contains(event.pos()) and \
               not self._send_btn.geometry().contains(event.pos()):
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            self._user_moved = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)
    # ── Paint — custom pill background ───────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg  = QColor(_BG_FOCUSED if self._focused else _BG_NORMAL)
        brd = QColor(_BORDER_FOCUS if self._focused else _BORDER_IDLE)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(),
                            _CORNER_R, _CORNER_R)
        painter.setPen(QPen(brd, 1.5))
        painter.setBrush(QBrush(bg))
        painter.drawPath(path)

        # Subtle drag handle — three dots on the left of the pill
        dot_col = QColor(_BORDER_IDLE)
        dot_col.setAlpha(160)
        painter.setBrush(QBrush(dot_col))
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            painter.drawEllipse(8, 14 + i * 7, 4, 4)

        painter.end()

    # ── Focus tracking ────────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if obj is self._input:
            if isinstance(event, QKeyEvent):
                if event.key() == Qt.Key.Key_Escape:
                    self._close_anim()
                    return True
        return super().eventFilter(obj, event)

    def focusInEvent(self, event) -> None:
        self._focused = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._focused = False
        self.update()
        super().focusOutEvent(event)

    def enterEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.unsetCursor()
        super().leaveEvent(event)
