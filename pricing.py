"""Model prices, cost estimates and the daily spending total."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Optional

logger = logging.getLogger("plugin.blind-accessibility-reader")
MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_MODEL = "google/gemini-3.1-flash-lite"
CURATED: list[dict[str, Any]] = [
    {"id": "qwen/qwen3.7-flash", "short": "Qwen 3.7 Flash", "prompt": 0.03e-6, "completion": 0.13e-6},
    {"id": "google/gemini-2.5-flash-lite", "short": "Gemini 2.5 Flash Lite", "prompt": 0.10e-6, "completion": 0.40e-6},
    {"id": "google/gemini-3.1-flash-lite", "short": "Gemini 3.1 Flash Lite", "prompt": 0.25e-6, "completion": 1.50e-6},
    {"id": "google/gemini-3.1-flash-image", "short": "Gemini 3.1 Flash Image", "prompt": 0.50e-6, "completion": 3.00e-6},
    {"id": "google/gemini-3.5-flash", "short": "Gemini 3.5 Flash", "prompt": 1.50e-6, "completion": 9.00e-6},
    {"id": "google/gemini-3.1-pro-preview", "short": "Gemini 3.1 Pro", "prompt": 2.00e-6, "completion": 12.00e-6},
    {"id": "google/gemma-4-26b-a4b-it:free", "short": "Gemma 4 free", "prompt": 0.0, "completion": 0.0},
]

IMAGE_IN, IMAGE_OUT = 450, 60
FRAME_IN, FRAME_OUT = 490, 50
GEMINI_IMAGE_IN, GEMINI_FRAME_IN = 1250, 1250
CALM_FRAMES_PER_MIN, BUSY_FRAMES_PER_MIN = 6, 20
REAL_AFTER = 20
EXPENSIVE_HOURLY_USD = 1.0
CACHE_SECONDS = 24 * 3600


def short_name(model_id: str) -> str:
    for m in CURATED:
        if m["id"] == model_id:
            return m["short"]
    return model_id.split("/", 1)[-1]


def money(usd: float) -> str:
    """Spoken amount, always in dollars so it can't be misread: '0.0004 dollars', '0.24 dollars', '1.42 dollars'."""
    if usd <= 0:
        return "0 dollars"
    if usd >= 0.01:
        text = f"{usd:.2f}"
    else:
        text = f"{usd:.1g}" if usd < 0.0001 else f"{usd:.4f}".rstrip("0")
        text = f"{float(text):.10f}".rstrip("0")
    return f"{text} dollars" if text != "1.00" else "1 dollar"


def cost_text(usd: float) -> str:
    """Short spoken price for one action: 'about 0.0004 dollars' or 'free'."""
    return "free" if usd <= 0 else f"about {money(usd)}"


def range_text(low: float, high: float) -> str:
    return "nothing, the model is free" if high <= 0 else f"{money(low)} to {money(high)}"


class Pricing:
    def __init__(self, ctx: Any, fetch=None):
        self._ctx = ctx
        self._fetch = fetch

    @property
    def _state(self) -> Any:
        return self._ctx.state

    def _table(self) -> dict[str, dict[str, float]]:
        cached = self._state.get("prices", default=None) or {}
        if cached and time.time() - cached.get("at", 0) < CACHE_SECONDS:
            return cached.get("models", {})
        models = self._download()
        if models:
            self._state.set("prices", {"at": time.time(), "models": models})
            return models
        return cached.get("models", {})

    def _download(self) -> dict[str, dict[str, float]]:
        try:
            if self._fetch is not None:
                data = self._fetch()
            else:
                import requests
                data = requests.get(MODELS_URL, timeout=10).json()
            out = {}
            for m in data.get("data", []):
                p = m.get("pricing") or {}
                try:
                    out[m["id"]] = {"prompt": float(p.get("prompt") or 0), "completion": float(p.get("completion") or 0),
                                    "image": float(p.get("image") or 0)}
                except (TypeError, ValueError):
                    continue
            return out
        except Exception as exc:
            logger.info("blind-accessibility-reader: price list unavailable: %s", exc)
            return {}

    def price(self, model_id: str) -> dict[str, float]:
        live = self._table().get(model_id)
        if live and live["prompt"] >= 0:
            return live
        for m in CURATED:
            if m["id"] == model_id:
                return {"prompt": m["prompt"], "completion": m["completion"], "image": 0.0}
        return {"prompt": 0.25e-6, "completion": 1.5e-6, "image": 0.0}

    def _averages(self, model_id: str, kind: str) -> tuple[float, float]:
        stats = (self._state.get("token_stats", default={}) or {}).get(f"{model_id}|{kind}")
        if stats and stats.get("n", 0) >= REAL_AFTER:
            return stats["in"] / stats["n"], stats["out"] / stats["n"]
        gemini = model_id.startswith("google/gemini")
        if kind == "image":
            return (GEMINI_IMAGE_IN if gemini else IMAGE_IN), IMAGE_OUT
        return (GEMINI_FRAME_IN if gemini else FRAME_IN), FRAME_OUT

    def call_cost(self, model_id: str, in_tokens: float, out_tokens: float, images: int = 1) -> float:
        p = self.price(model_id)
        return in_tokens * p["prompt"] + out_tokens * p["completion"] + images * p.get("image", 0.0)

    def image_cost(self, model_id: str) -> float:
        return self.call_cost(model_id, *self._averages(model_id, "image"))

    def frame_cost(self, model_id: str) -> float:
        return self.call_cost(model_id, *self._averages(model_id, "frame"))

    def hour_range(self, model_id: str) -> tuple[float, float]:
        f = self.frame_cost(model_id)
        return f * CALM_FRAMES_PER_MIN * 60, f * BUSY_FRAMES_PER_MIN * 60

    def video_range(self, model_id: str, seconds: Optional[float]) -> tuple[float, float]:
        low, high = self.hour_range(model_id)
        hours = (seconds / 3600) if seconds else 1.0
        return low * hours, high * hours

    def is_expensive(self, model_id: str) -> bool:
        return self.hour_range(model_id)[1] > EXPENSIVE_HOURLY_USD

    def price_line(self, model_id: str) -> str:
        img = self.image_cost(model_id)
        low, high = self.hour_range(model_id)
        name = short_name(model_id)
        if img <= 0:
            return f"{name} is free but rate limited, so it is best for testing."
        per_dollar = int(round(1 / img, -2)) if img < 0.01 else int(1 / img)
        return (f"With {name}, 1 dollar covers about {per_dollar:,} images. "
                f"An hour of video costs {money(low)} to {money(high)}.")

    def model_options(self) -> list[dict[str, Any]]:
        out = []
        for m in CURATED:
            low, high = self.hour_range(m["id"])
            img = self.image_cost(m["id"])
            label = (f"{m['short']}. Free and rate limited, for testing." if img <= 0 else
                     f"{m['short']}. {cost_text(img).capitalize()} an image, {money(low)} to {money(high)} an hour of video.")
            out.append({"id": m["id"], "short": m["short"], "label": label, "expensive": self.is_expensive(m["id"]),
                        "hour_text": money(high)})
        return out

    def record(self, model_id: str, kind: str, in_tokens: int, out_tokens: int) -> float:
        cost = self.call_cost(model_id, in_tokens, out_tokens)
        stats = dict(self._state.get("token_stats", default={}) or {})
        s = dict(stats.get(f"{model_id}|{kind}", {"n": 0, "in": 0, "out": 0}))
        s["n"] += 1
        s["in"] += in_tokens
        s["out"] += out_tokens
        stats[f"{model_id}|{kind}"] = s
        self._state.set("token_stats", stats)
        ledger = dict(self._state.get("ledger", default={}) or {})
        today = date.today().isoformat()
        ledger = {today: ledger.get(today, 0.0) + cost}
        self._state.set("ledger", ledger)
        return cost

    def spent_today(self) -> float:
        ledger = self._state.get("ledger", default={}) or {}
        return float(ledger.get(date.today().isoformat(), 0.0))
