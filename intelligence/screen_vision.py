"""
screen_vision.py — Give Buddy eyes.

Captures the screen, sends it to a local Ollama vision model, and returns
a short in-character observation. Runs entirely in a background thread so
the UI is never blocked.

Supported models (tried in order of preference):
    moondream, gemma3:4b, gemma3:12b, llava, llava-phi3, bakllava

If no vision model is available, on_done is called with None and the caller
can suggest: ollama pull moondream
"""

from __future__ import annotations

import base64
import io
import threading
import logging
from typing import Callable

import requests
from PIL import Image, ImageGrab

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
_OLLAMA_URL = "http://localhost:11434"
_MAX_PX      = 768      # resize screenshot to this before sending
_TIMEOUT_S   = 45       # inference timeout
_NUM_PREDICT = 60       # max tokens in response

# Ordered preference — first match wins
_VISION_MODELS = [
    "moondream",
    "gemma3:4b",
    "gemma3:12b",
    "gemma3:27b",
    "llava-phi3",
    "llava",
    "bakllava",
    "minicpm-v",
]

_PROMPT = (
    "You are a small excitable dog looking at a computer screen. "
    "Describe ONE specific thing you can clearly see right now — "
    "such as the app name, window title, video being watched, code being written, "
    "or any visible error or notification. "
    "Only mention things actually on screen. Do NOT guess or make things up. "
    "React in dog character. Maximum 15 words."
)

# ── Internal state ─────────────────────────────────────────────────────────────
_cached_model: str | None = None   # discovered model, cached for speed
_discovery_lock = threading.Lock()


# ── Model discovery ───────────────────────────────────────────────────────────

def _discover_vision_model() -> str | None:
    """Query Ollama /api/tags and return the first available vision model."""
    global _cached_model
    with _discovery_lock:
        if _cached_model:
            return _cached_model
        try:
            r = requests.get(f"{_OLLAMA_URL}/api/tags", timeout=5)
            r.raise_for_status()
            pulled = [m["name"] for m in r.json().get("models", [])]
        except Exception as exc:
            log.warning("[vision] Ollama unreachable: %s", exc)
            return None

        for preferred in _VISION_MODELS:
            pref_base = preferred.split(":")[0]
            pref_tag  = preferred.split(":")[1] if ":" in preferred else None
            for pulled_name in pulled:
                pull_base = pulled_name.split(":")[0]
                pull_tag  = pulled_name.split(":")[1] if ":" in pulled_name else None
                if pref_base != pull_base:
                    continue
                # If preferred specifies a tag (e.g. "gemma3:4b"), require exact
                # match — prevents gemma3:1b matching gemma3:4b
                if pref_tag is not None and pull_tag != pref_tag:
                    continue
                _cached_model = pulled_name
                log.info("[vision] Using model: %s", _cached_model)
                return _cached_model

        log.info("[vision] No vision model found. Run: ollama pull moondream")
        return None


def reset_model_cache() -> None:
    """Force re-discovery next time (call after user pulls a new model)."""
    global _cached_model
    _cached_model = None


# ── Screenshot ────────────────────────────────────────────────────────────────

def _capture_b64(max_px: int = _MAX_PX) -> str:
    """
    Grab the full screen, resize so the longest edge ≤ max_px, 
    encode as base64 JPEG.
    """
    img: Image.Image = ImageGrab.grab()
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ── Main API ──────────────────────────────────────────────────────────────────

def peek(on_done: Callable[[str | None], None]) -> None:
    """
    Non-blocking. Takes a screenshot, asks the vision model, then calls
    on_done(text) on a background thread.

    on_done receives:
        str   — Buddy's observation (ready to pass to window.say)
        None  — no vision model available or inference failed
    """
    def _run() -> None:
        model = _discover_vision_model()
        if not model:
            on_done(None)
            return
        try:
            log.info("[vision] Capturing screen …")
            img_b64 = _capture_b64()
            log.info("[vision] Querying %s …", model)
            resp = requests.post(
                f"{_OLLAMA_URL}/api/generate",
                json={
                    "model":   model,
                    "prompt":  _PROMPT,
                    "images":  [img_b64],
                    "stream":  False,
                    "options": {
                        "temperature": 0.75,
                        "num_predict": _NUM_PREDICT,
                    },
                },
                timeout=_TIMEOUT_S,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            if text:
                log.info("[vision] Response: %s", text[:80])
                on_done(text)
            else:
                on_done(None)
        except requests.exceptions.HTTPError as exc:
            # 500 usually means model is still loading/downloading — clear cache
            # so we re-discover a working model next time
            if exc.response is not None and exc.response.status_code >= 500:
                log.warning("[vision] Model %s not ready (server error) — will retry later", model)
                reset_model_cache()
            else:
                log.warning("[vision] HTTP error: %s", exc)
            on_done(None)
        except requests.exceptions.Timeout:
            log.warning("[vision] Inference timed out after %ss", _TIMEOUT_S)
            on_done(None)
        except Exception as exc:
            log.warning("[vision] Error: %s", exc)
            on_done(None)

    threading.Thread(target=_run, daemon=True, name="BuddyVision").start()
