"""
pet_window.py — The transparent, always-on-top, click-through pet window.

Key behaviours:
  - Frameless + fully transparent background
  - Click-through on transparent pixels via WS_EX_TRANSPARENT (Windows)
  - Clicks on opaque sprite pixels are captured (drag / pet interactions)
  - Animates sprite sheets loaded from assets/sprites/
  - Displays speech bubbles for SLM responses
  - Moves around the screen driven by PetBrain + movement engine
"""

from __future__ import annotations
import random
import time
from pathlib import Path

import ctypes
import ctypes.wintypes
import win32con
import win32gui

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QSize, pyqtSlot, pyqtSignal
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QFontMetrics, QPen, QPainterPath
from PyQt6.QtWidgets import QWidget, QApplication

from pet.brain import PetBrain, PetState, STATE_SPRITE, DIRECTIONAL_STATES
from system.throttle import ThrottleLevel
from audio import engine as sound_engine
from system.paths import SPRITES_DIR as ASSETS
from ui.bubble_widget import BubbleWidget
from ui.chat_bar import ChatBar


class SpriteSheet:
    """Slices a horizontal sprite strip into individual QPixmap frames."""

    def __init__(self, path: Path, frame_w: int = 32, frame_h: int = 32,
                 scale: int = 3) -> None:
        self._frames: list[QPixmap] = []
        if path.exists():
            sheet = QPixmap(str(path))
            count = sheet.width() // frame_w
            for i in range(count):
                frame = sheet.copy(i * frame_w, 0, frame_w, frame_h)
                self._frames.append(
                    frame.scaled(frame_w * scale, frame_h * scale,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.FastTransformation)
                )
        else:
            # fallback: single coloured square
            px = QPixmap(frame_w * scale, frame_h * scale)
            px.fill(QColor(210, 160, 80, 200))
            self._frames = [px]

    def __len__(self) -> int:
        return len(self._frames)

    def frame(self, index: int) -> QPixmap:
        return self._frames[index % len(self._frames)]

    @property
    def size(self) -> QSize:
        return self._frames[0].size() if self._frames else QSize(96, 96)


class PetWindow(QWidget):
    """The pet widget — transparent, always-on-top, click-through background."""

    double_clicked = pyqtSignal(str)   # emits user message (may be empty)
    treat_reached  = pyqtSignal()      # Buddy reached the bone/treat
    petted         = pyqtSignal()      # user held click >= 1 s

    FRAME_W = 56
    FRAME_H = 48
    SCALE   = 2   # 56x48px → 112x96 on screen

    def __init__(self, cfg: dict, brain: PetBrain) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                               Qt.WindowType.WindowStaysOnTopHint |
                               Qt.WindowType.Tool)

        self._cfg    = cfg
        self._brain  = brain
        self._facing_right = True

        # Position
        screen = QApplication.primaryScreen().geometry()
        self._screen_rect = screen
        self._pos = QPoint(screen.width() // 2, screen.height() - 120)

        # Movement
        pet_cfg = cfg.get("pet", {})
        self._base_speed     = float(pet_cfg.get("speed", 2.0))
        self._wander_dir     = QPoint(1, 0)
        self._wander_timer   = QTimer(self)
        self._wander_timer.timeout.connect(self._pick_new_direction)
        self._wander_timer.start(int(pet_cfg.get("wander_interval_s", 4) * 1000))

        # Sprite sheets
        self._sheets: dict[str, SpriteSheet] = {}
        self._load_sprites()

        # Animation
        self._frame_idx = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._next_frame)
        self._fps = int(cfg.get("pet", {}).get("fps_full", 12))
        self._anim_timer.start(1000 // self._fps)

        # Movement tick — 50ms (20fps) keeps the pet visibly slow and clickable
        self._move_timer = QTimer(self)
        self._move_timer.timeout.connect(self._move_tick)
        self._move_timer.start(50)

        # Speech bubble (overlay widget — replaces the old painted-on bubble)
        self._bubble_widget = BubbleWidget(self)

        # Chat bar (floating input)
        self._chat_bar = ChatBar()
        self._chat_bar.anchor_to(self)

        # Keep a back-compat reference so external code that checks
        # `self._window._bubble` (e.g. skill guards) still works.
        # The property below maps to the widget's visibility.
        self._bubble: bool = False

        # Drag state
        self._drag_offset = QPoint(0, 0)
        self._is_dragging = False
        self._press_time  = 0.0    # monotonic timestamp of last mouse-press
        self._hovered     = False  # True while cursor is over pet

        # Petting hand animation
        self._petting_active = False
        self._pet_phase      = 0.0
        self._pet_timer      = QTimer(self)
        self._pet_timer.setInterval(40)   # ~25 fps — smooth stroke
        self._pet_timer.timeout.connect(self._pet_anim_tick)

        # Treat / fetch chase
        self._chase_target: QPoint | None = None   # screen centre to run toward

        # Chain — movement radius constraint
        self._chain_anchor: QPoint | None = None   # centre of allowed zone
        self._chain_radius: int = 180              # max pixels from anchor

        # Jump physics
        self._jump_active   = False
        self._jump_vy       = 0.0    # vertical velocity (negative = upward)
        self._jump_gravity  = 1.5   # px/tick² acceleration downward
        self._jump_origin_y = 0     # Y position before jump started

        # Live tail wag
        self._tail_phase = 0.0

        # Window setup
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
        sprite_size = QSize(self.FRAME_W * self.SCALE, self.FRAME_H * self.SCALE)
        self.resize(sprite_size)
        self.move(self._pos)

        # Keep _bubble sentinel in sync with BubbleWidget visibility
        self._bubble_widget.destroyed.connect(lambda: setattr(self, '_bubble', False))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Remove Windows 11 rounded corner decoration
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_DONOTROUND = 1
            hwnd = int(self.winId())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(ctypes.c_int(DWMWCP_DONOTROUND)),
                ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass

    def _load_sprites(self) -> None:
        names = [
            "walk_right", "walk_left", "run_right", "run_left",
            "idle", "sleep", "watch", "excited", "grabbed", "dance",
            # Phase 1
            "sit_right", "sit_left",
            "jump_right", "jump_left",
            "paw_right",  "paw_left",
            "scratch",    "stretch",
        ]
        for name in names:
            self._sheets[name] = SpriteSheet(
                ASSETS / f"{name}.png", self.FRAME_W, self.FRAME_H, self.SCALE
            )

    def _current_sheet_key(self) -> str:
        state = self._brain.state
        key = STATE_SPRITE.get(state, "idle")
        if state in DIRECTIONAL_STATES:
            key = f"{key}_{'right' if self._facing_right else 'left'}"
        return key

    # ------------------------------------------------------------------ #
    # Paint                                                                #
    # ------------------------------------------------------------------ #

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        sheet = self._sheets.get(self._current_sheet_key())
        if sheet:
            frame = sheet.frame(self._frame_idx)
            painter.drawPixmap(0, 0, frame)

        self._draw_tail(painter)

        # Petting hand drawn over the sprite while mouse is held
        if self._petting_active:
            import math
            pw = self.FRAME_W * self.SCALE
            ph = self.FRAME_H * self.SCALE
            hx = pw // 2 - 8 + int(math.sin(self._pet_phase) * 22)
            hy = int(ph * 0.08)
            painter.setFont(QFont("Segoe UI Emoji", 15))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawText(hx, hy + 20, "\U0001f91a\U0001f3fb")

        painter.end()

    # ------------------------------------------------------------------ #
    # Live tail                                                            #
    # ------------------------------------------------------------------ #

    def _tail_wag_speed(self) -> float:
        """Radians added to tail phase each animation frame."""
        state = self._brain.state
        if state == PetState.SLEEP:
            return 0.0
        if state in (PetState.EXCITED, PetState.DANCE):
            return 0.35
        if state in (PetState.WALK, PetState.RUN, PetState.JUMP):
            return 0.22
        if state in (PetState.SIT, PetState.SCRATCH):
            return 0.07
        return 0.14   # IDLE, WATCH, GRABBED, PAW, STRETCH

    def _tail_wag_amp(self) -> float:
        """Peak pixel swing of the tail tip."""
        state = self._brain.state
        if state == PetState.SLEEP:
            return 0.0
        if state in (PetState.EXCITED, PetState.DANCE):
            return 20.0
        if state in (PetState.WALK, PetState.RUN, PetState.JUMP):
            return 14.0
        if state == PetState.SIT:
            return 8.0
        return 11.0

    def _draw_tail(self, painter: QPainter) -> None:
        """Overlay a smooth bezier tail that wags live, independent of sprite."""
        import math

        amp  = self._tail_wag_amp()
        wag  = math.sin(self._tail_phase) * amp
        oy   = 0
        pw   = self.FRAME_W * self.SCALE   # 112
        state = self._brain.state

        if self._facing_right:
            bx, by = 18, 52 + oy          # rear haunch base (aligns with pixel art)
            if state == PetState.SLEEP:   # drooped: tail hangs down
                cx, cy = 8,  60 + oy
                tx, ty = 5,  65 + oy
            else:
                cx, cy = 8,  38 + oy + wag * 0.45
                tx, ty = 10, 26 + oy + wag
        else:
            bx, by = pw - 18, 52 + oy
            if state == PetState.SLEEP:
                cx, cy = pw - 8,  60 + oy
                tx, ty = pw - 5,  65 + oy
            else:
                cx, cy = pw - 8,  38 + oy + wag * 0.45
                tx, ty = pw - 10, 26 + oy + wag

        path = QPainterPath()
        path.moveTo(bx, by)
        path.quadTo(cx, cy, tx, ty)

        # Brown body-colour stroke
        pen = QPen(QColor(110, 65, 18, 210), 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Cream/white fluffy tip — last 40 % of the tail
        tip_pen = QPen(QColor(240, 228, 196, 200), 4)
        tip_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(tip_pen)
        tip_path = QPainterPath()
        tip_path.moveTo(cx + (tx - cx) * 0.6, cy + (ty - cy) * 0.6)
        tip_path.lineTo(tx, ty)
        painter.drawPath(tip_path)

    # ------------------------------------------------------------------ #
    # Animation timer                                                      #
    # ------------------------------------------------------------------ #

    @pyqtSlot()
    def _next_frame(self) -> None:
        sheet = self._sheets.get(self._current_sheet_key())
        if sheet:
            self._frame_idx = (self._frame_idx + 1) % len(sheet)
        self._tail_phase += self._tail_wag_speed()
        self.update()

    # ------------------------------------------------------------------ #
    # Movement                                                             #
    # ------------------------------------------------------------------ #

    def chase(self, target_centre: QPoint) -> None:
        """Tell Buddy to run toward a screen point (treat/fetch bone centre)."""
        self._chase_target = target_centre
        self._brain.force_run()

    def set_chain(self, anchor: QPoint, radius: int = 180) -> None:
        """Constrain Buddy's wandering to a circle of `radius` px around `anchor`."""
        self._chain_anchor = anchor
        self._chain_radius = radius

    def remove_chain(self) -> None:
        """Let Buddy roam freely again."""
        self._chain_anchor = None

    def stop_chase(self) -> None:
        self._chase_target = None

    def walk_toward(self, target: QPoint) -> None:
        """Gently redirect wander direction toward target (cursor following)."""
        if self._chase_target is not None or self._is_dragging:
            return
        pet_cx = self._pos.x() + (self.FRAME_W * self.SCALE) // 2
        pet_cy = self._pos.y() + (self.FRAME_H * self.SCALE) // 2
        dx = target.x() - pet_cx
        dy = target.y() - pet_cy
        if (dx * dx + dy * dy) ** 0.5 < 60:
            return   # already close
        nx = 1 if dx > 8 else (-1 if dx < -8 else 0)
        ny = 1 if dy > 8 else (-1 if dy < -8 else 0)
        if nx == 0 and ny == 0:
            return
        self._wander_dir = QPoint(nx, ny)
        self._facing_right = nx >= 0

    @pyqtSlot()
    def _move_tick(self) -> None:
        # Don't move while a bubble is showing — movement undoes the window shift
        if self._bubble:
            return
        # Stop wandering while cursor is over the pet (still allows chase)
        if self._hovered and self._chase_target is None:
            return

        # ── Directed chase (treat / fetch) ─────────────────────────────
        if self._chase_target is not None:
            self._chase_step()
            return

        state = self._brain.state

        # ── JUMP: horizontal wander + vertical parabola ───────────────────
        if state == PetState.JUMP:
            self._do_jump_tick()
            return

        if state in (PetState.IDLE, PetState.SLEEP, PetState.WATCH,
                     PetState.EXCITED, PetState.GRABBED, PetState.DANCE,
                     PetState.SIT, PetState.SCRATCH, PetState.STRETCH,
                     PetState.PAW):
            return

        speed = self._base_speed
        if state == PetState.RUN:
            speed *= 2.5
        if self._brain.throttle == ThrottleLevel.REDUCED:
            speed *= 0.5

        dx = self._wander_dir.x() * speed
        dy = self._wander_dir.y() * speed

        new_x = int(self._pos.x() + dx)
        new_y = int(self._pos.y() + dy)

        # Bounce off screen edges
        sw, sh = self._screen_rect.width(), self._screen_rect.height()
        pw, ph = self.FRAME_W * self.SCALE, self.FRAME_H * self.SCALE

        bounced = False
        if new_x < 0:
            new_x = 0
            self._wander_dir.setX(abs(self._wander_dir.x()))
            bounced = True
        elif new_x + pw > sw:
            new_x = sw - pw
            self._wander_dir.setX(-abs(self._wander_dir.x()))
            bounced = True
        if new_y < 0:
            new_y = 0
            self._wander_dir.setY(abs(self._wander_dir.y()))
            bounced = True
        elif new_y + ph > sh:
            new_y = sh - ph
            self._wander_dir.setY(-abs(self._wander_dir.y()))
            bounced = True

        if bounced:
            self._frame_idx = 0
            # Screen-edge PAW: 40 % chance Buddy bats the wall when wandering
            if (state == PetState.WALK and random.random() < 0.40
                    and (new_x <= 2 or new_x + pw >= sw - 2)):
                self._brain.do_paw()
                return

        self._facing_right = self._wander_dir.x() >= 0
        self._pos = QPoint(new_x, new_y)

        # ── Chain constraint: clamp to anchor radius ─────────────────
        if self._chain_anchor is not None:
            ca  = self._chain_anchor
            pcx = new_x + pw // 2
            pcy = new_y + ph // 2
            cdx = pcx - ca.x()
            cdy = pcy - ca.y()
            dist_c = (cdx * cdx + cdy * cdy) ** 0.5
            if dist_c > self._chain_radius:
                ratio  = self._chain_radius / dist_c
                new_x  = int(ca.x() + cdx * ratio - pw // 2)
                new_y  = int(ca.y() + cdy * ratio - ph // 2)
                # Bounce direction back toward anchor
                self._wander_dir = QPoint(
                    -1 if cdx > 0 else 1,
                    -1 if cdy > 0 else 1,
                )
                self._pos = QPoint(new_x, new_y)

        self.move(self._pos)

    def _chase_step(self) -> None:
        """Move one step toward _chase_target. Emit treat_reached when close."""
        target = self._chase_target
        pet_cx = self._pos.x() + (self.FRAME_W * self.SCALE) // 2
        pet_cy = self._pos.y() + (self.FRAME_H * self.SCALE) // 2
        dx = target.x() - pet_cx
        dy = target.y() - pet_cy
        dist = (dx * dx + dy * dy) ** 0.5

        if dist < 24:   # close enough — treat reached
            self._chase_target = None
            self._brain.on_grab_end()   # back to idle/walk
            self.treat_reached.emit()
            return

        speed = self._base_speed * 2.5   # run speed
        ratio = speed / dist
        new_x = int(self._pos.x() + dx * ratio)
        new_y = int(self._pos.y() + dy * ratio)

        # Clamp to screen
        sw, sh = self._screen_rect.width(), self._screen_rect.height()
        pw, ph = self.FRAME_W * self.SCALE, self.FRAME_H * self.SCALE
        new_x = max(0, min(new_x, sw - pw))
        new_y = max(0, min(new_y, sh - ph))

        self._facing_right = dx >= 0
        self._pos = QPoint(new_x, new_y)
        self.move(self._pos)

    def _do_jump_tick(self) -> None:
        """Advance one tick of jump physics: horizontal wander + vertical parabola."""
        sw, sh = self._screen_rect.width(), self._screen_rect.height()
        pw, ph = self.FRAME_W * self.SCALE, self.FRAME_H * self.SCALE

        # Horizontal component — same as normal walk
        dx = self._wander_dir.x() * self._base_speed
        new_x = int(self._pos.x() + dx)
        new_x = max(0, min(new_x, sw - pw))

        # Vertical component — parabolic arc
        self._jump_vy += self._jump_gravity
        new_y = int(self._pos.y() + self._jump_vy)

        if new_y >= self._jump_origin_y:   # touched ground
            new_y = self._jump_origin_y
            self._jump_active = False
            self._jump_vy = 0.0
            self._brain.on_jump_landed()

        self._facing_right = self._wander_dir.x() >= 0
        self._pos = QPoint(new_x, new_y)
        self.move(self._pos)

    def do_jump(self) -> None:
        """Public: trigger a hop from the current ground position."""
        if self._jump_active or self._is_dragging:
            return
        self._jump_origin_y = self._pos.y()
        self._jump_vy = -15.0
        self._jump_active = True
        self._brain.do_jump()

    @pyqtSlot()
    def _pick_new_direction(self) -> None:
        if self._brain.state not in (PetState.WALK, PetState.RUN):
            return
        angle_choices = [
            QPoint(1, 0), QPoint(-1, 0), QPoint(0, 1), QPoint(0, -1),
            QPoint(1, 1), QPoint(-1, 1), QPoint(1, -1), QPoint(-1, -1),
        ]
        self._wander_dir = random.choice(angle_choices)

    # ------------------------------------------------------------------ #
    # Mouse events                                                         #
    # ------------------------------------------------------------------ #

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.unsetCursor()
        # Stop petting if mouse left without releasing
        if self._petting_active:
            self._petting_active = False
            self._pet_timer.stop()
            self.update()
        super().leaveEvent(event)

    def _pet_anim_tick(self) -> None:
        """Advance the petting stroke oscillation."""
        self._pet_phase += 0.22
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_offset = event.pos()
            self._press_time  = time.monotonic()
            self._brain.on_grab_start()
            self._frame_idx = 0
            # Show petting hand animation
            self._petting_active = True
            self._pet_phase = 0.0
            self._pet_timer.start()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._is_dragging:
            new_pos = self.mapToParent(event.pos() - self._drag_offset)
            self._pos = new_pos
            self.move(new_pos)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            held = time.monotonic() - self._press_time
            self._is_dragging = False
            self._brain.on_grab_end()
            # Stop petting animation
            self._petting_active = False
            self._pet_timer.stop()
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if self._hovered
                else Qt.CursorShape.ArrowCursor
            )
            self.update()
            if held >= 1.0:   # held 1+ second = petting
                self.petted.emit()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self._brain.on_grab_end()
            self._brain.on_click()
            self._frame_idx = 0
            # Open floating chat bar instead of blocking QInputDialog
            if self._chat_bar.isVisible():
                self._chat_bar.popup()   # re-focus if already open
            else:
                self._chat_bar.popup()
                # Emit empty string so caller knows a chat session started
                # (the bar emits message_sent when user presses Enter)

    # ------------------------------------------------------------------ #
    # Speech bubble                                                        #
    # ------------------------------------------------------------------ #

    def say(self, text: str, duration_ms: int = 9000, sound: str = "bark") -> None:
        """Show a speech bubble. sound='bark'|'yip'|'whimper'|'none'."""
        if sound == "bark":
            sound_engine.bark()
        elif sound == "yip":
            sound_engine.excited_yip()
        elif sound == "whimper":
            sound_engine.whimper()
        self._bubble = True
        self._bubble_widget.show_text(text, duration_ms)
        # Update sentinel when bubble hides
        def _clear_bubble():
            self._bubble = False
        self._bubble_widget._anim_out_a.finished.connect(_clear_bubble)

    # ------------------------------------------------------------------ #
    # Throttle response                                                    #
    # ------------------------------------------------------------------ #

    @pyqtSlot(object)
    def on_throttle_changed(self, level: ThrottleLevel) -> None:
        fps_map = {
            ThrottleLevel.FULL:    self._cfg.get("pet", {}).get("fps_full",    12),
            ThrottleLevel.REDUCED: self._cfg.get("pet", {}).get("fps_reduced",  6),
            ThrottleLevel.MINIMAL: 3,
            ThrottleLevel.SLEEP:   2,
        }
        fps = fps_map.get(level, 6)
        self._anim_timer.setInterval(1000 // fps)
        if level in (ThrottleLevel.MINIMAL, ThrottleLevel.SLEEP):
            self._move_timer.stop()
        else:
            if not self._move_timer.isActive():
                self._move_timer.start(50)
