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
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import QWidget, QApplication, QInputDialog, QLineEdit

from pet.brain import PetBrain, PetState, STATE_SPRITE, DIRECTIONAL_STATES
from system.throttle import ThrottleLevel
from audio import engine as sound_engine

ASSETS = Path(__file__).parent.parent / "assets" / "sprites"


class SpeechBubble:
    """Renders a speech bubble above the pet."""

    def __init__(self, text: str, duration_ms: int = 5000) -> None:
        self.text       = text
        self.duration_ms = duration_ms
        self.remaining  = duration_ms

    def tick(self, elapsed_ms: int) -> bool:
        """Returns True while still alive."""
        self.remaining -= elapsed_ms
        return self.remaining > 0

    @property
    def alpha(self) -> int:
        """Fade out in last 800ms."""
        if self.remaining < 800:
            return max(0, int(255 * self.remaining / 800))
        return 255


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

        # Speech bubble
        self._bubble: SpeechBubble | None = None
        self._bubble_timer = QTimer(self)
        self._bubble_timer.timeout.connect(self._bubble_tick)

        # Drag state
        self._drag_offset = QPoint(0, 0)
        self._is_dragging = False
        self._press_time  = 0.0    # monotonic timestamp of last mouse-press
        self._bubble_offset_y = 0  # how much window was shifted up for bubble
        self._hovered     = False  # True while cursor is over pet or bubble

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

        # Window setup
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
        sprite_size = QSize(self.FRAME_W * self.SCALE, self.FRAME_H * self.SCALE)
        self.resize(sprite_size)
        self.move(self._pos)

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
            painter.drawPixmap(0, self._bubble_offset_y, frame)

        if self._bubble and self._bubble.remaining > 0:
            self._draw_bubble(painter)

        # Petting hand drawn over the sprite while mouse is held
        if self._petting_active:
            import math
            pw = self.FRAME_W * self.SCALE
            ph = self.FRAME_H * self.SCALE
            hx = pw // 2 - 8 + int(math.sin(self._pet_phase) * 22)
            hy = self._bubble_offset_y + int(ph * 0.08)
            painter.setFont(QFont("Segoe UI Emoji", 15))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawText(hx, hy + 20, "\U0001f91a\U0001f3fb")

        painter.end()

    def _draw_bubble(self, painter: QPainter) -> None:
        bubble = self._bubble
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text  = bubble.text
        max_w = 220
        # Word-wrap manually
        lines: list[str] = []
        words = text.split()
        line  = ""
        for w in words:
            test = (line + " " + w).strip()
            if fm.horizontalAdvance(test) > max_w:
                lines.append(line)
                line = w
            else:
                line = test
        if line:
            lines.append(line)

        line_h  = fm.height() + 2
        pad     = 8
        bw      = max(fm.horizontalAdvance(l) for l in lines) + pad * 2
        bh      = line_h * len(lines) + pad * 2
        bx      = max(0, (self.width() - bw) // 2)

        # Always draw bubble in lower portion of window (sprite is at offset_y)
        sprite_h = self.FRAME_H * self.SCALE
        if self._bubble_offset_y > 0:
            # Bubble is ABOVE sprite (window shifted up): draw at top
            by = 6
        else:
            # Bubble is BELOW sprite: draw after sprite
            by = sprite_h + 8

        alpha = bubble.alpha
        bg    = QColor(255, 255, 220, min(220, alpha))
        border= QColor(100, 80, 40, alpha)

        painter.setBrush(bg)
        painter.setPen(border)
        painter.drawRoundedRect(bx, by, bw, bh, 8, 8)

        painter.setPen(QColor(40, 30, 10, alpha))
        for i, l in enumerate(lines):
            painter.drawText(bx + pad, by + pad + fm.ascent() + i * line_h, l)

    # ------------------------------------------------------------------ #
    # Animation timer                                                      #
    # ------------------------------------------------------------------ #

    @pyqtSlot()
    def _next_frame(self) -> None:
        sheet = self._sheets.get(self._current_sheet_key())
        if sheet:
            self._frame_idx = (self._frame_idx + 1) % len(sheet)
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
            # Dialog must be WindowStaysOnTopHint or it hides behind the pet
            dlg = QInputDialog()
            dlg.setWindowFlags(
                Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
            )
            dlg.setWindowTitle("Talk to Buddy 🐾")
            dlg.setLabelText("Say something to Buddy:")
            dlg.setInputMode(QInputDialog.InputMode.TextInput)
            dlg.setTextEchoMode(QLineEdit.EchoMode.Normal)
            dlg.resize(360, 120)
            dlg.activateWindow()
            dlg.raise_()
            if dlg.exec():
                text = dlg.textValue().strip()
            else:
                text = ""
            self.double_clicked.emit(text)

    # ------------------------------------------------------------------ #
    # Speech bubble                                                        #
    # ------------------------------------------------------------------ #

    def say(self, text: str, duration_ms: int = 9000, sound: str = "bark") -> None:
        """Show a speech bubble. sound='bark'|'yip'|'whimper'|'none'."""
        # Play the attention sound
        if sound == "bark":
            sound_engine.bark()
        elif sound == "yip":
            sound_engine.excited_yip()
        elif sound == "whimper":
            sound_engine.whimper()
        self._bubble = SpeechBubble(text, duration_ms)
        self._bubble_timer.start(100)
        # Compute bubble dimensions
        font = QFont("Segoe UI", 9)
        fm = QFontMetrics(font)
        max_w = 240
        words = text.split()
        lines, line = [], ""
        for w in words:
            test = (line + " " + w).strip()
            if fm.horizontalAdvance(test) > max_w:
                lines.append(line); line = w
            else:
                line = test
        if line:
            lines.append(line)
        bw = max(fm.horizontalAdvance(l) for l in lines) + 20
        bh = (fm.height() + 2) * len(lines) + 20
        sprite_w = self.FRAME_W * self.SCALE
        sprite_h = self.FRAME_H * self.SCALE
        win_w = max(sprite_w, bw + 10)
        win_h = sprite_h + bh + 16
        # If pet is in bottom half of screen, shift window up so bubble shows above
        screen_h = self._screen_rect.height()
        if self._pos.y() + sprite_h + bh + 16 > screen_h - 20:
            # Draw bubble above: move window up by bubble height
            new_y = max(0, self._pos.y() - bh - 16)
            self._bubble_offset_y = self._pos.y() - new_y
            self.move(self._pos.x(), new_y)
            self.resize(win_w, win_h)
        else:
            self._bubble_offset_y = 0
            self.resize(win_w, win_h)
        self.update()

    @pyqtSlot()
    def _bubble_tick(self) -> None:
        # Pause countdown while the cursor is over the pet/bubble
        if self._hovered:
            # Keep opacity full so text stays readable
            if self._bubble and self._bubble.remaining < 1200:
                self._bubble.remaining = 1200
            self.update()
            return
        if self._bubble and not self._bubble.tick(100):
            self._bubble = None
            self._bubble_offset_y = 0
            self._bubble_timer.stop()
            self.move(self._pos)
            self.resize(self.FRAME_W * self.SCALE, self.FRAME_H * self.SCALE)
        self.update()
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
