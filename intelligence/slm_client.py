"""
slm_client.py — Non-blocking Ollama client using LangChain.
Runs inference in a QThread worker so it never stalls the main thread.
Falls back gracefully if Ollama is not running, and supports tool execution.
"""

from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from collections import deque
from typing import Callable, Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

OLLAMA_BASE = "http://127.0.0.1:11434"

# ── Cached availability (never block the main thread) ─────────────────────────
_avail_cache: dict = {"ok": False, "ts": 0.0}
_AVAIL_TTL = 10.0   # seconds before re-checking


def _ollama_available() -> bool:
    """Blocking check — only call from a background thread."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3):
            return True
    except Exception:
        return False


def _cached_available() -> bool:
    """Non-blocking: returns last known status. Never waits."""
    return _avail_cache["ok"]


def _refresh_availability_async() -> None:
    """Spin a daemon thread to update the cache without blocking the caller."""
    import threading

    def _check() -> None:
        result = _ollama_available()
        _avail_cache["ok"] = result
        _avail_cache["ts"] = time.monotonic()

    t = threading.Thread(target=_check, daemon=True)
    t.start()


def list_ollama_models() -> list[str]:
    """Return names of models currently pulled in Ollama, or [] if unreachable.
    Blocking — only call from a background thread or at user request."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read())
        return sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
    except Exception:
        return []


class _InferenceWorker(QObject):
    """Runs in a dedicated QThread using LangChain ChatOllama."""

    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, model: str, prompt: str, system: str, history: list[tuple[str, str]], client: SLMClient, timeout: int = 30) -> None:
        super().__init__()
        self.model  = model
        self.prompt = prompt
        self.system = system
        self.history = history
        self.client = client
        self.timeout = timeout

    def run(self) -> None:
        try:
            # Lazy import LangChain to prevent startup block
            from langchain_ollama import ChatOllama
            from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
            from intelligence.tools import get_tools

            print(f"[SLM Worker] Initializing ChatOllama for model: {self.model}")
            llm = ChatOllama(
                model=self.model,
                temperature=0.8,
                timeout=self.timeout
            )

            tools = get_tools(self.client)

            # Build conversational message list
            messages = [SystemMessage(content=self.system)]
            for user_msg, buddy_reply in self.history:
                messages.append(HumanMessage(content=user_msg))
                messages.append(AIMessage(content=buddy_reply))
            messages.append(HumanMessage(content=self.prompt))

            # Bind tools
            try:
                llm_with_tools = llm.bind_tools(tools)
                response = llm_with_tools.invoke(messages)
            except Exception as exc:
                print(f"[SLM Worker] Tool binding failed (model may not support tools), falling back to direct chat: {exc}")
                response = llm.invoke(messages)

            # Manual ReAct loop for tool execution
            if hasattr(response, "tool_calls") and response.tool_calls:
                messages.append(response)
                print(f"[SLM Worker] Model requested tool execution: {response.tool_calls}")

                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]

                    tool_obj = next((t for t in tools if t.name == tool_name), None)
                    if tool_obj:
                        try:
                            print(f"[SLM Worker] Executing tool '{tool_name}' with args {tool_args}")
                            result = tool_obj.invoke(tool_args)
                            print(f"[SLM Worker] Tool '{tool_name}' result: {result}")
                        except Exception as e:
                            result = f"Error executing tool: {e}"
                    else:
                        result = f"Tool '{tool_name}' not found."

                    messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

                # Get final response combining tool output
                final_response = llm.invoke(messages)
                text = final_response.content
            else:
                text = response.content

            print(f"[SLM Worker] Completed inference successfully.")
            self.finished.emit(text)

        except Exception as exc:
            print(f"[SLM Worker] Inference failed: {exc}")
            # Differentiate network issues vs timeout
            if not _ollama_available():
                self.error.emit("OLLAMA_DOWN")
            else:
                self.error.emit("TIMEOUT")


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
        self._cfg = cfg
        slm_cfg = cfg.get("slm", {})
        self._model    = slm_cfg.get("text_model", "gemma3:1b")
        self._enabled  = slm_cfg.get("backend", "ollama") != "disabled"
        # Minimum timeout is now 15s instead of forcing 300s
        self._timeout  = max(slm_cfg.get("response_timeout_s", 15), 15)
        self._busy     = False
        self._thread: QThread | None = None
        self._worker: _InferenceWorker | None = None
        name = username if username else "friend"
        self._name = name
        self._mood_desc = ""
        self._system_prompt = self._make_system_prompt()
        self._history: deque[tuple[str, str]] = deque(maxlen=5)  # (user_msg, buddy_reply)
        
        # Tools callback registry
        self._tools_callbacks: dict[str, Callable[[], str] | Callable[[str], str]] = {}
        
        # Heavy model warning flag
        self.slow_model_warning = False

        # Prime availability cache
        if self._enabled:
            _refresh_availability_async()

    def register_tool_callback(self, name: str, callback: Callable) -> None:
        """Register a callback for LangChain tools to interact with system/UI."""
        self._tools_callbacks[name] = callback

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
        """Non-blocking — returns last cached status."""
        return self._enabled and _cached_available()

    def ask(self, prompt: str, on_done: Callable[[str], None],
            on_error: Callable[[str], None] | None = None,
            track_history: bool = True) -> None:
        """Non-blocking. on_done called on main thread via Qt signal."""
        if self._busy:
            print("[SLM] busy, skipping request")
            if on_error:
                on_error("SLM is busy")
            return
        if not self._enabled:
            if on_error:
                on_error("SLM disabled")
            return

        age = time.monotonic() - _avail_cache["ts"]
        if age > _AVAIL_TTL:
            _refresh_availability_async()
        if not _cached_available():
            print("[SLM] Ollama not reachable (cached)")
            if on_error:
                on_error("Ollama not running")
            return

        print(f"[SLM] asking: {prompt[:60]}")
        self._busy   = True
        self._thread = QThread()
        
        # Build worker with history and client reference
        self._worker = _InferenceWorker(
            self._model,
            prompt,
            self._make_system_prompt(),
            list(self._history) if track_history else [],
            self,
            timeout=self._timeout
        )
        self._worker.moveToThread(self._thread)

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

    # ────────────────────────────────────────────────────────────────── #

    def _done(self, text: str, callback: Callable[[str], None],
              user_turn: str | None = None) -> None:
        self._busy = False
        self.slow_model_warning = False  # Reset on successful reply
        
        # Remove any thinking blocks (e.g. <think>...</think>)
        import re
        cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        if user_turn is not None:
            self._history.append((user_turn, cleaned_text))
        self._cleanup()
        callback(cleaned_text)
        
        # Ollama is reachable, update availability cache
        _avail_cache["ok"] = True
        _avail_cache["ts"] = time.monotonic()

    def _fail(self, err: str, callback: Callable[[str], None] | None) -> None:
        self._busy = False
        self._cleanup()

        if err == "TIMEOUT":
            # Attempt fallback to an installed lightweight model
            installed = list_ollama_models()
            lightweight_fallbacks = [
                "gemma3:1b", "llama3.2:1b", "gemma2:2b", "tinyllama",
                "phi3:mini", "llama3.2:3b", "gemma3:4b", "qwen2.5:1.5b", "qwen2.5:3b"
            ]
            fallback_model = None
            for model_name in lightweight_fallbacks:
                match = next((m for m in installed if model_name in m.lower()), None)
                if match and match != self._model:
                    fallback_model = match
                    break

            if fallback_model:
                print(f"[SLM] Model timed out. Falling back from '{self._model}' to '{fallback_model}'")
                original_model = self._model
                self.set_model(fallback_model)
                self.slow_model_warning = False
                
                # Apply fallback to config
                self._cfg.setdefault("slm", {})["text_model"] = fallback_model
                
                if callback:
                    callback(f"FALLBACK:{fallback_model}:{original_model}")
                return
            else:
                print("[SLM] Model timed out. No lightweight fallback available.")
                self.slow_model_warning = True
                if callback:
                    callback("TIMEOUT_NO_FALLBACK")
                return

        elif err == "OLLAMA_DOWN":
            if callback:
                callback("OLLAMA_DOWN")
            return

        if callback:
            callback(f"[{err}]")

    def _cleanup(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait() # Ensure thread is completely exited
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
