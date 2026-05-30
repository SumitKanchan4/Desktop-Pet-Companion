"""
slm_client.py — Non-blocking Ollama client.
Runs inference in a QThread worker so it never stalls the main thread.
Falls back gracefully if Ollama is not running or model not pulled.
"""

from __future__ import annotations
import json
import urllib.request
import urllib.error
from collections import deque
from typing import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal


OLLAMA_BASE = "http://localhost:11434"


def _ollama_available() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3):
            return True
    except Exception:
        return False


def list_ollama_models() -> list[str]:
    """Return names of models currently pulled in Ollama, or [] if unreachable."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read())
        return sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
    except Exception:
        return []


class _InferenceWorker(QObject):
    """Runs in a dedicated QThread."""

    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, model: str, prompt: str, system: str) -> None:
        super().__init__()
        self.model  = model
        self.prompt = prompt
        self.system = system

    def run(self) -> None:
        payload = json.dumps({
            "model":  self.model,
            "prompt": self.prompt,
            "system": self.system,
            "stream": False,
            "options": {"num_predict": 80, "temperature": 0.8},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                text = data.get("response", "").strip()
                print(f"[SLM] response: {text[:80]}")
                self.finished.emit(text)
        except urllib.error.URLError as exc:
            print(f"[SLM] URLError: {exc}")
            self.error.emit(f"Ollama unreachable: {exc}")
        except Exception as exc:
            print(f"[SLM] Error: {exc}")
            self.error.emit(str(exc))


class SLMClient(QObject):
    """
    Public API for the pet to get LLM responses.
    All calls are async — provide a callback that receives the text.
    """

    SYSTEM_PROMPT_TEMPLATE = (
        "You are Buddy, an adorable desktop dog pet belonging to {name}. "
        "You are playful, loyal, sometimes cheeky, and always supportive. "
        "Keep replies very short (1\u20132 sentences max). "
        "Address your owner by name ({name}) occasionally but naturally \u2014 not every message. "
        "React in character to what {name} says or what they're doing on screen. "
        "Occasionally use dog sounds like 'Woof!' or 'Bork!' naturally."
    )

    def __init__(self, cfg: dict, username: str = "friend",
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        slm_cfg = cfg.get("slm", {})
        self._model    = slm_cfg.get("text_model", "gemma3:1b")
        # Default to enabled; degrades gracefully if Ollama isn't reachable.
        self._enabled  = slm_cfg.get("backend", "ollama") != "disabled"
        self._timeout  = slm_cfg.get("response_timeout_s", 15)
        self._busy     = False
        self._thread: QThread | None = None
        self._worker: _InferenceWorker | None = None
        name = username if username else "friend"
        self._name = name
        self._mood_desc = ""
        self._system_prompt = self._make_system_prompt()
        self._history: deque[tuple[str, str]] = deque(maxlen=5)  # (user_msg, buddy_reply)

    def _make_system_prompt(self) -> str:
        from datetime import datetime
        hour = datetime.now().hour
        if 5 <= hour < 12:
            time_ctx = "It's morning — Buddy is energetic and eager to start the day."
        elif 12 <= hour < 17:
            time_ctx = "It's afternoon — Buddy is playful and in good spirits."
        elif 17 <= hour < 21:
            time_ctx = "It's evening — Buddy is cozy, warm, and affectionate."
        else:
            time_ctx = "It's late at night — Buddy is sleepy but loyally staying up."

        base = self.SYSTEM_PROMPT_TEMPLATE.format(name=self._name)
        base += f" {time_ctx}"
        if self._mood_desc:
            base += f" Right now Buddy is feeling {self._mood_desc}."
        return base

    def set_mood(self, mood_description: str) -> None:
        """Update Buddy's current mood in the system prompt."""
        self._mood_desc = mood_description
        self._system_prompt = self._make_system_prompt()

    def set_username(self, name: str) -> None:
        """Hot-update the owner name used in the system prompt."""
        self._name = name.strip() or "friend"
        self._system_prompt = self._make_system_prompt()

    def set_model(self, model: str) -> None:
        """Hot-swap the text model. Takes effect on next request."""
        if model:
            self._model = model

    def set_enabled(self, enabled: bool) -> None:
        """Toggle SLM on/off without restart."""
        self._enabled = bool(enabled)

    @property
    def available(self) -> bool:
        return self._enabled and _ollama_available()

    def ask(self, prompt: str, on_done: Callable[[str], None],
            on_error: Callable[[str], None] | None = None,
            track_history: bool = True) -> None:
        """Non-blocking. on_done called on main thread via Qt signal.

        track_history=True  — prepends last 5 exchanges and stores this one.
        track_history=False — stateless call (context comments, reminders).
        """
        if self._busy:
            print("[SLM] busy, skipping request")
            return
        if not self._enabled:
            if on_error:
                on_error("SLM disabled")
            return

        # Check availability (fast, 3s timeout)
        if not _ollama_available():
            print("[SLM] Ollama not reachable")
            if on_error:
                on_error("Ollama not running")
            return

        full_prompt = self._build_prompt(prompt, track_history)
        print(f"[SLM] asking: {prompt[:60]}")
        self._busy   = True
        self._thread = QThread()
        # Rebuild system prompt fresh (captures current time-of-day + mood)
        self._worker = _InferenceWorker(self._model, full_prompt, self._make_system_prompt())
        self._worker.moveToThread(self._thread)

        # Store the user turn now; reply stored in _done
        _user_turn = prompt if track_history else None

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(
            lambda text: self._done(text, on_done, _user_turn)
        )
        self._worker.error.connect(lambda err: self._fail(err, on_error))

        self._thread.start()

    def context_comment(self, context_label: str, window_title: str,
                        on_done: Callable[[str], None]) -> None:
        """Ask pet to comment on what the user is currently doing."""
        prompt = (
            f"The user is currently {context_label.lower()} "
            f"(window: '{window_title[:80]}'). "
            "Make a brief, in-character comment about it."
        )
        self.ask(prompt, on_done, track_history=False)

    def break_reminder(self, minutes: int, username: str = "friend",
                       on_done: Callable[[str], None] = None) -> None:
        prompt = (
            f"{username} has been working non-stop for {minutes} minutes. "
            "Remind them to take a break \u2014 be cute but insistent."
        )
        self.ask(prompt, on_done, track_history=False)

    # ------------------------------------------------------------------ #

    def _build_prompt(self, current: str, use_history: bool) -> str:
        """Prepend last N exchanges as a mini transcript."""
        if not use_history or not self._history:
            return current
        lines = []
        for user_msg, buddy_reply in self._history:
            lines.append(f"{user_msg}")
            lines.append(f"Buddy: {buddy_reply}")
        lines.append(current)
        return "\n".join(lines)

    def _done(self, text: str, callback: Callable[[str], None],
              user_turn: str | None = None) -> None:
        self._busy = False
        # Store exchange in history
        if user_turn is not None:
            self._history.append((user_turn, text))
        self._cleanup()
        callback(text)

    def _fail(self, err: str, callback: Callable[[str], None] | None) -> None:
        self._busy = False
        self._cleanup()
        if callback:
            callback(f"[{err}]")

    def _cleanup(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None
