"""
settings_dialog.py — Runtime Settings UI for Buddy.

Accessible from the system tray (Settings…). Lets the user change:
  * Owner name
  * SLM backend on/off
  * Text model (populated from Ollama's installed model list)
  * Vision: enabled + model
  * Voice / barks on-off (audio.enabled)

Behaviour:
  * Live "Ollama: connected / not running" status with a Refresh button.
  * Save writes config.yaml to disk and emits ``settings_saved(cfg)``.
  * The caller hot-applies what it can; remaining changes apply on restart.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from intelligence.slm_client import list_ollama_models, _ollama_available
import system.autostart as _autostart


# Fallback model lists used when Ollama is unreachable so the dropdowns
# still offer sensible choices (the user may install them later).
FALLBACK_TEXT_MODELS = ["gemma3:1b", "gemma3:4b", "phi3:mini", "llama3.2:3b", "tinyllama"]
FALLBACK_VISION_MODELS = ["moondream", "llava-phi3", "llava", "gemma3:4b"]


class SettingsDialog(QDialog):
    """Modal Settings dialog. Emits ``settings_saved(cfg)`` on accept."""

    settings_saved = pyqtSignal(dict)

    def __init__(self, cfg: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._installed_models: list[str] = []

        self.setWindowTitle("Buddy — Settings")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)

        # ── Ollama status row ────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self._status_label = QLabel()
        self._status_label.setTextFormat(Qt.TextFormat.RichText)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_models)
        status_row.addWidget(self._status_label, 1)
        status_row.addWidget(refresh_btn, 0)
        root.addLayout(status_row)

        # ── Form ─────────────────────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(8)

        self._name_edit = QLineEdit(cfg.get("user", {}).get("name", ""))
        self._name_edit.setPlaceholderText("Your name")
        form.addRow("Your name:", self._name_edit)

        slm_cfg = cfg.get("slm", {})

        self._slm_enabled = QCheckBox("Use Ollama for chat & commentary")
        self._slm_enabled.setChecked(slm_cfg.get("backend", "ollama") != "disabled")
        form.addRow("", self._slm_enabled)

        self._text_combo = QComboBox()
        self._text_combo.setEditable(True)  # allow typing model names not yet pulled
        self._text_hint_label = QLabel()
        self._text_hint_label.setWordWrap(True)
        self._text_hint_label.setTextFormat(Qt.TextFormat.RichText)
        form.addRow("Text model:", self._text_combo)
        form.addRow("", self._text_hint_label)

        self._vision_enabled = QCheckBox("Let Buddy peek at the screen")
        self._vision_enabled.setChecked(bool(slm_cfg.get("vision_enabled", False)))
        form.addRow("", self._vision_enabled)

        self._vision_combo = QComboBox()
        self._vision_combo.setEditable(True)
        self._vision_hint_label = QLabel()
        self._vision_hint_label.setWordWrap(True)
        self._vision_hint_label.setTextFormat(Qt.TextFormat.RichText)
        form.addRow("Vision model:", self._vision_combo)
        form.addRow("", self._vision_hint_label)

        self._text_combo.currentTextChanged.connect(self._update_text_hint)
        self._text_combo.editTextChanged.connect(self._update_text_hint)
        self._vision_combo.currentTextChanged.connect(self._update_vision_hint)
        self._vision_combo.editTextChanged.connect(self._update_vision_hint)

        self._audio_enabled = QCheckBox("Play barks and sounds")
        self._audio_enabled.setChecked(
            bool(cfg.get("audio", {}).get("enabled", True))
        )
        form.addRow("", self._audio_enabled)

        self._autostart_enabled = QCheckBox("Start Buddy when Windows starts")
        self._autostart_enabled.setChecked(_autostart.is_enabled())
        # Apply the registry change immediately when the user toggles so it
        # takes effect even if they cancel the rest of the dialog.
        self._autostart_enabled.toggled.connect(_autostart.apply)
        form.addRow("", self._autostart_enabled)

        self._updates_enabled = QCheckBox("Automatically check for updates")
        self._updates_enabled.setChecked(
            bool(cfg.get("app", {}).get("auto_update", True))
        )
        form.addRow("", self._updates_enabled)

        root.addLayout(form)

        # ── Hint ─────────────────────────────────────────────────────────────
        hint = QLabel(
            "<small><i>Name & enable-flags apply immediately. "
            "Model changes take effect on next Buddy message.</i></small>"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ── Buttons ──────────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # Initial populate
        self._refresh_models()

    # ────────────────────────────────────────────────────────────────────────

    def _refresh_models(self) -> None:
        """Re-query Ollama and repopulate the model dropdowns."""
        self._installed_models = list_ollama_models()
        installed = self._installed_models
        connected = _ollama_available()

        slm_cfg = self._cfg.get("slm", {})
        current_text = self._text_combo.currentText() or slm_cfg.get("text_model", "gemma3:1b")
        current_vision = self._vision_combo.currentText() or slm_cfg.get("vision_model", "moondream")

        if connected:
            count = len(installed)
            self._status_label.setText(
                f"<span style='color:#2a8a2a;'>● Ollama connected</span> "
                f"&nbsp; <small>({count} model{'s' if count != 1 else ''} installed)</small>"
            )
            text_options = installed or FALLBACK_TEXT_MODELS
            vision_options = installed or FALLBACK_VISION_MODELS
        else:
            self._status_label.setText(
                "<span style='color:#b03030;'>● Ollama not running</span> "
                "&nbsp; <small>Start Ollama, then click Refresh</small>"
            )
            text_options = FALLBACK_TEXT_MODELS
            vision_options = FALLBACK_VISION_MODELS

        self._populate_combo(self._text_combo, text_options, current_text)
        self._populate_combo(self._vision_combo, vision_options, current_vision)

        # Force hint update after populating combo boxes
        self._update_text_hint(self._text_combo.currentText())
        self._update_vision_hint(self._vision_combo.currentText())

    @staticmethod
    def _populate_combo(combo: QComboBox, options: list[str], current: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(options)
        if current and combo.findText(current) < 0:
            combo.addItem(current)
        if current:
            combo.setCurrentText(current)
        combo.blockSignals(False)

    # ────────────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        """Mutate the in-memory cfg dict, emit signal, and close."""
        cfg = self._cfg
        cfg.setdefault("user", {})["name"] = self._name_edit.text().strip()

        slm = cfg.setdefault("slm", {})
        slm["backend"] = "ollama" if self._slm_enabled.isChecked() else "disabled"
        slm["text_model"] = self._text_combo.currentText().strip() or "gemma3:1b"
        slm["vision_enabled"] = self._vision_enabled.isChecked()
        slm["vision_model"] = self._vision_combo.currentText().strip() or "moondream"

        cfg.setdefault("audio", {})["enabled"] = self._audio_enabled.isChecked()
        cfg.setdefault("app", {})["auto_update"] = self._updates_enabled.isChecked()
        # autostart is applied immediately on toggle — no extra work needed here

        self.settings_saved.emit(cfg)
        self.accept()

    def _get_model_suitability_html(self, model_name: str) -> str:
        """Classify model size/name and return rich warning or recommendation HTML."""
        model_name = model_name.strip()
        if not model_name:
            return ""

        # 1. If Ollama is connected, check if the model is pulled/installed
        connected = _ollama_available()
        if connected and self._installed_models:
            is_installed = any(model_name.lower() in m.lower() for m in self._installed_models)
            if not is_installed:
                return "<span style='color:#d9534f;'>⚠️ Model not pulled: Ollama will download this on first request, causing a long initial delay.</span>"

        # 2. Check for size indicator keywords to warn about load times/hardware lag
        name_lower = model_name.lower()
        
        # Extremely Heavy models (>13B parameters)
        heavy_keywords = ["13b", "14b", "30b", "32b", "33b", "70b", "72b", "command-r", "deepseek-coder:33b"]
        if any(kw in name_lower for kw in heavy_keywords):
            return "<span style='color:#d9534f;'>❌ Extremely heavy model: Likely to cause lags/timeouts unless run on high-end hardware.</span>"
            
        # Medium / Heavy models (4B - 9B parameters)
        medium_keywords = ["4b", "7b", "8b", "9b", "llama3", "mistral", "gemma:7b", "gemma2:9b"]
        if any(kw in name_lower for kw in medium_keywords):
            return "<span style='color:#f0ad4e;'>⚠️ Heavy model: May load slowly or lag on standard hardware (GPU recommended).</span>"
            
        # Lightweight / recommended models (1B - 3B parameters)
        light_keywords = ["1b", "2b", "3b", "mini", "tiny", "gemma3:1b", "llama3.2:1b", "llama3.2:3b", "phi3:mini", "qwen2.5:1.5b", "qwen2.5:3b"]
        if any(kw in name_lower for kw in light_keywords):
            return "<span style='color:#5cb85c;'>✓ Lightweight & fast (Recommended for smooth pet play)</span>"
            
        # Unknown/General fallback
        return "<span style='color:#777777;'>ℹ️ Model suitability unspecified. Recommend 1B - 3B models for real-time responsiveness.</span>"

    def _update_text_hint(self, text: str) -> None:
        self._text_hint_label.setText(self._get_model_suitability_html(text))

    def _update_vision_hint(self, text: str) -> None:
        self._vision_hint_label.setText(self._get_model_suitability_html(text))
