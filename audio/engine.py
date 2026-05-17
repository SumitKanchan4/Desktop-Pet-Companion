"""
sound_engine.py — Canine SFX for Buddy.

bark()  — formant synthesis (sawtooth glottal source + scipy IIR bandpass).
          Uses scipy when available for the most realistic result; falls back
          to a resonator-convolution approach without scipy.
Others  — lightweight numpy-only synthesis.

Requires: numpy + sounddevice  (pip install numpy sounddevice)
Optional: scipy                (pip install scipy)   — improves bark quality
Degrades gracefully to silence if numpy/sounddevice are missing.
"""

from __future__ import annotations
import os
import threading
import time
import wave

_AVAILABLE = False
_sd        = None
_np        = None

try:
    import numpy as _numpy
    import sounddevice as _sounddevice
    _np = _numpy
    _sd = _sounddevice
    _AVAILABLE = True
except ImportError:
    pass

SAMPLE_RATE = 22050

_BARK_WAV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "bark.wav")


def is_available() -> bool:
    return _AVAILABLE


# ── Helpers ─────────────────────────────────────────────────────────────────

def _play_async(samples) -> None:
    if not _AVAILABLE:
        return
    def _run():
        try:
            _sd.play(samples, SAMPLE_RATE, blocking=True)
            _sd.wait()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _adsr(n: int, a=0.05, d=0.15, s=0.60, r=0.20):
    na = max(1, int(n * a)); nd = max(1, int(n * d))
    nr = max(1, int(n * r)); ns = max(0, n - na - nd - nr)
    return _np.concatenate([
        _np.linspace(0.0, 1.0, na), _np.linspace(1.0, s, nd),
        _np.full(ns, s), _np.linspace(s, 0.0, nr),
    ])[:n]


def _norm(wave, volume=0.70):
    return (wave / (_np.max(_np.abs(wave)) + 1e-9) * volume).astype(_np.float32)


# ── Public SFX ───────────────────────────────────────────────────────────────

def bark(volume: float = 0.72) -> None:
    """Play bark.wav fresh from disk each call — never stale."""
    if not _AVAILABLE or not os.path.exists(_BARK_WAV_PATH):
        return
    try:
        with wave.open(_BARK_WAV_PATH) as wf:
            pcm = _np.frombuffer(wf.readframes(wf.getnframes()), dtype=_np.int16)
        data = (pcm.astype(_np.float32) / 32768.0 * volume)
        _play_async(data.astype(_np.float32))
    except Exception:
        pass


def excited_yip(count: int = 2, volume: float = 0.65) -> None:
    """Quick high-pitched yips — treat caught / excited."""
    if not _AVAILABLE:
        return
    def _seq():
        for i in range(count):
            n    = int(SAMPLE_RATE * 0.11)
            freq = _np.linspace(1150 - i * 130, 520 - i * 90, n)
            ph   = 2 * _np.pi * _np.cumsum(freq) / SAMPLE_RATE
            w    = _np.sin(ph) + 0.25 * _np.random.randn(n)
            w   *= _adsr(n, a=0.02, d=0.10, s=0.35, r=0.53)
            _sd.play(_norm(w, volume), SAMPLE_RATE, blocking=True)
            _sd.wait()
            time.sleep(0.07)
    threading.Thread(target=_seq, daemon=True).start()


def whimper(volume: float = 0.50) -> None:
    """Sad wavering whimper — loneliness."""
    if not _AVAILABLE:
        return
    n    = int(SAMPLE_RATE * 0.50)
    t    = _np.linspace(0, 0.50, n)
    freq = 530 - 70 * t + 45 * _np.sin(2 * _np.pi * 5.5 * t)
    ph   = 2 * _np.pi * _np.cumsum(freq) / SAMPLE_RATE
    w    = _np.sin(ph) + 0.09 * _np.random.randn(n)
    w   *= _adsr(n, a=0.12, d=0.08, s=0.68, r=0.12)
    _play_async(_norm(w, volume))


def sniff(volume: float = 0.42) -> None:
    """Brief nasal sniff — treat appears."""
    if not _AVAILABLE:
        return
    n   = int(SAMPLE_RATE * 0.13)
    raw = _np.random.randn(n)
    w   = _np.diff(raw, prepend=raw[0])
    w  *= _adsr(n, a=0.08, d=0.28, s=0.48, r=0.16)
    _play_async(_norm(w, volume))


def growl(volume: float = 0.55) -> None:
    """Low rumbling growl — alert."""
    if not _AVAILABLE:
        return
    n   = int(SAMPLE_RATE * 0.35)
    t   = _np.linspace(0, 0.35, n)
    freq = 120 + 30 * _np.sin(2 * _np.pi * 8 * t)
    ph   = 2 * _np.pi * _np.cumsum(freq) / SAMPLE_RATE
    w    = _np.sin(ph) + 0.55 * _np.sin(ph * 2.1) + 0.30 * _np.random.randn(n)
    w   *= _adsr(n, a=0.08, d=0.12, s=0.72, r=0.08)
    _play_async(_norm(w, volume))
