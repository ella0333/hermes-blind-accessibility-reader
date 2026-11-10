"""Reader settings and the spending guard."""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from .pricing import DEFAULT_MODEL

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "mode": "manual",
    "readouts": True,
    "output": "screen_reader", # screen_reader, browser_voice or hermes_voice
    "captions": False,
    "chime": True,
    "read_titles": False,
    "replace_alt": False,
    "model": DEFAULT_MODEL,
    "ceiling": 0.50,
    "video_cap": 0.05,
    "per_minute": 20,
    "setup_done": False,
}
CHOICES = {
    "mode": ("manual", "auto"),
    "output": ("screen_reader", "browser_voice", "hermes_voice"),
}
STORAGE_KEYS = {"model": "vision_model"}


class Settings:
    def __init__(self, ctx: Any):
        self._ctx = ctx

    def get(self, key: str) -> Any:
        value = self._ctx.get_config(STORAGE_KEYS.get(key, key), default=DEFAULTS[key])
        return DEFAULTS[key] if value is None else value

    def all(self) -> dict[str, Any]:
        return {k: self.get(k) for k in DEFAULTS}

    def set(self, key: str, value: Any) -> Any:
        if key not in DEFAULTS:
            raise KeyError(key)
        if key in CHOICES and value not in CHOICES[key]:
            raise ValueError(f"{key} must be one of {', '.join(CHOICES[key])}")
        if key in ("enabled", "readouts", "setup_done", "captions", "read_titles", "replace_alt", "chime"):
            value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "on", "yes")
        elif key in ("ceiling", "video_cap"):
            value = max(0.0, float(value))
        elif key == "per_minute":
            value = max(1, int(value))
        self._ctx.set_config(STORAGE_KEYS.get(key, key), value)
        return value


class Guard:
    """Per-minute cap and daily ceiling. say() is called once per trip, never repeatedly."""

    def __init__(self, settings: Settings, pricing: Any):
        self._settings = settings
        self._pricing = pricing
        self._recent: deque[float] = deque()
        self._warned: set[str] = set()

    def check(self, upcoming_cost: float) -> tuple[bool, str]:
        """Return (allowed, message to read once or '')."""
        now = time.time()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        cap = int(self._settings.get("per_minute"))
        if len(self._recent) >= cap:
            return False, self._once("minute", f"Paused: {cap} descriptions this minute. It picks up again in a moment.")
        ceiling = float(self._settings.get("ceiling"))
        spent = self._pricing.spent_today()
        if upcoming_cost > 0 and spent + upcoming_cost > ceiling:
            return False, self._once("ceiling", f"Stopped: today's ceiling of {_m(ceiling)} is reached. "
                                                f"Raise it in settings with Alt+Shift+S to keep going.")
        self._warned.discard("minute")
        return True, ""

    def note_call(self) -> None:
        self._recent.append(time.time())

    def threshold_message(self) -> str:
        ceiling = float(self._settings.get("ceiling"))
        if ceiling <= 0:
            return ""
        spent = self._pricing.spent_today()
        for pct in (90, 50):
            if spent >= ceiling * pct / 100:
                return self._once(f"pct{pct}", f"You have used {pct} percent of today's {_m(ceiling)} ceiling.")
        return ""

    def reset_ceiling_warning(self) -> None:
        self._warned -= {"ceiling", "pct50", "pct90"}

    def _once(self, key: str, text: str) -> str:
        if key in self._warned:
            return ""
        self._warned.add(key)
        return text


def _m(usd: float) -> str:
    from .pricing import money
    return money(usd)
