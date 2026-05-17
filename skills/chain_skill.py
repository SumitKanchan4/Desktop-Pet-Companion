"""chain_skill.py — Chain/leash feature: pins Buddy to a draggable anchor."""
from __future__ import annotations

from PyQt6.QtCore import QPoint

from ui.chain_anchor import ChainAnchor


class ChainSkill:
    """Manages the chain that constrains Buddy's wandering radius."""

    def __init__(self, window, tray, cfg: dict) -> None:
        self._window = window
        self._tray   = tray
        self._cfg    = cfg
        self._anchor: ChainAnchor | None = None

    def on_chain_toggled(self) -> None:
        if self._anchor is not None:
            # Unchain
            self._anchor.vanish()
            self._anchor = None
            self._window.remove_chain()
            self._tray.set_chain_text("⛓️  Chain here")
            self._window.say("FREE! 🐾 *zooms around the screen*", duration_ms=3000, sound="yip")
        else:
            # Chain at Buddy's current centre
            pw = self._window.FRAME_W * self._window.SCALE
            ph = self._window.FRAME_H * self._window.SCALE
            anchor_pt = QPoint(
                self._window._pos.x() + pw // 2,
                self._window._pos.y() + ph // 2,
            )
            radius = self._cfg.get("pet", {}).get("chain_radius", 180)
            self._anchor = ChainAnchor(anchor_pt)
            self._anchor.moved.connect(self._window.set_chain)
            self._window.set_chain(anchor_pt, radius)
            self._tray.set_chain_text("🔓  Unchain Buddy")
            self._window.say(
                "*looks at chain* Okay fine... I'll stay here 🐶",
                duration_ms=4000, sound="none",
            )
