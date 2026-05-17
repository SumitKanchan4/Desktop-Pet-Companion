"""
weather.py — Fetch current weather via wttr.in (no API key, auto-geolocation).

Usage:
    from weather import WeatherData, fetch

    fetch(on_done=lambda w: print(w.buddy_summary()))
"""

from __future__ import annotations

import threading
import logging
from dataclasses import dataclass
from typing import Callable

import requests

log = logging.getLogger(__name__)

_URL = "https://wttr.in/?format=j1"
_TIMEOUT = 10


@dataclass
class WeatherData:
    condition:    str    # e.g. "Sunny", "Light rain", "Partly cloudy"
    temp_c:       float
    feels_like_c: float
    humidity:     int
    wind_kmph:    int
    location:     str

    # ── Derived helpers ────────────────────────────────────────────────

    def is_hot(self)        -> bool: return self.temp_c >= 33
    def is_warm(self)       -> bool: return 22 <= self.temp_c < 33
    def is_cool(self)       -> bool: return 10 <= self.temp_c < 22
    def is_cold(self)       -> bool: return self.temp_c < 10
    def is_freezing(self)   -> bool: return self.temp_c < 0
    def is_rainy(self)      -> bool: return any(w in self.condition.lower() for w in ("rain", "drizzle", "shower"))
    def is_snowy(self)      -> bool: return "snow" in self.condition.lower() or "blizzard" in self.condition.lower()
    def is_stormy(self)     -> bool: return any(w in self.condition.lower() for w in ("thunder", "storm"))
    def is_sunny(self)      -> bool: return any(w in self.condition.lower() for w in ("sunny", "clear"))
    def is_cloudy(self)     -> bool: return any(w in self.condition.lower() for w in ("cloud", "overcast", "fog", "mist"))
    def is_windy(self)      -> bool: return self.wind_kmph >= 40

    def buddy_summary(self) -> str:
        """One-line summary for SLM context injection."""
        loc = f" in {self.location}" if self.location else ""
        return (
            f"{self.condition}{loc}, {self.temp_c:.0f}°C "
            f"(feels {self.feels_like_c:.0f}°C), "
            f"humidity {self.humidity}%, wind {self.wind_kmph} km/h"
        )

    def buddy_reaction(self) -> tuple[str, str]:
        """
        Returns (message, sound) — Buddy's in-character weather reaction.
        sound is one of: 'bark', 'yip', 'none'
        """
        c = self.condition
        if self.is_snowy():
            return ("IT'S SNOWING!! ❄️🐾 Can we go outside?? Please??", "bark")
        if self.is_stormy():
            return ("There's a storm out there! ⛈️ *hides under desk*", "none")
        if self.is_rainy():
            return (f"It's {c.lower()} outside 🌧️  Perfect stay-in-and-code weather!", "none")
        if self.is_freezing():
            return (f"It's {self.temp_c:.0f}°C outside!! 🥶 *shivers* Stay warm, Sumit!", "none")
        if self.is_cold():
            return (f"Brr! Only {self.temp_c:.0f}°C out there 🧥 Blanket weather!", "none")
        if self.is_hot():
            return (f"It's {self.temp_c:.0f}°C outside! 🌞 Scorching! Lucky we're inside!", "yip")
        if self.is_sunny() and self.is_warm():
            return (f"Beautiful {self.temp_c:.0f}°C and sunny! ☀️ What a lovely day!", "yip")
        if self.is_windy():
            return (f"Super windy outside! 💨 My ears would be flapping!", "none")
        if self.is_cloudy():
            return (f"{c} today ☁️  Cozy indoor vibes!", "none")
        # Generic fallback
        return (f"{c}, {self.temp_c:.0f}°C outside 🌤️", "none")


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch(on_done: Callable[[WeatherData | None], None]) -> None:
    """
    Non-blocking. Fetches weather in a background thread, then calls
    on_done(WeatherData) on success or on_done(None) on failure.
    """
    def _run() -> None:
        try:
            r = requests.get(
                _URL,
                timeout=_TIMEOUT,
                headers={"User-Agent": "curl/7.68.0"},  # wttr.in prefers curl UA
            )
            r.raise_for_status()
            data  = r.json()
            cc    = data["current_condition"][0]
            areas = data.get("nearest_area", [{}])
            area  = areas[0].get("areaName",  [{}])[0].get("value", "") if areas else ""
            country = areas[0].get("country", [{}])[0].get("value", "") if areas else ""
            loc   = ", ".join(filter(None, [area, country]))
            result = WeatherData(
                condition=cc["weatherDesc"][0]["value"],
                temp_c=float(cc["temp_C"]),
                feels_like_c=float(cc["FeelsLikeC"]),
                humidity=int(cc["humidity"]),
                wind_kmph=int(cc["windspeedKmph"]),
                location=loc,
            )
            log.info("[weather] %s", result.buddy_summary())
            on_done(result)
        except Exception as exc:
            log.warning("[weather] Fetch failed: %s", exc)
            on_done(None)

    threading.Thread(target=_run, daemon=True, name="BuddyWeather").start()
