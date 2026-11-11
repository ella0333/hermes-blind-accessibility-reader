"""Settings, prices, descriptions and narration for the browser extension."""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional

from .describer import BLACK_FRAME, FRAME_WIDTH, IMAGE_MAX, Describer, changed, fetch_image, is_black, shrink, signature
from .pricing import Pricing, cost_text, money, range_text, short_name
from .settings import Guard, Settings

logger = logging.getLogger("plugin.blind-accessibility-reader")
LONG_VIDEO_SECONDS = 600
SETTING_KEYS = ("enabled", "mode", "readouts", "output", "model", "ceiling", "video_cap", "captions", "read_titles", "replace_alt", "chime")


class Service:
    def __init__(self, ctx: Any, settings: Settings, pricing: Pricing, on_model_change: Callable[[str], None]):
        self._ctx = ctx
        self.settings = settings
        self.pricing = pricing
        self.guard = Guard(settings, pricing)
        self.describer = Describer(ctx)
        self._on_model_change = on_model_change
        self._lock = threading.Lock()
        self._cache: dict[str, str] = {}
        self._narrations: dict[str, dict] = {}
        self.recent: deque[tuple[float, str]] = deque(maxlen=8)
        self.last_seen = 0.0
        self._pending: deque[dict] = deque()
        self._results: dict[str, str] = {}
        self._result_event = threading.Condition()

    def status(self) -> dict:
        s = self.settings.all()
        model = s["model"]
        spent, ceiling = self.pricing.spent_today(), float(s["ceiling"])
        return {
            "settings": {k: s[k] for k in SETTING_KEYS} | {"setup_done": s["setup_done"]},
            "image_text": cost_text(self.pricing.image_cost(model)),
            "frame_cost": self.pricing.frame_cost(model),
            "model_short": short_name(model),
            "price_line": self.pricing.price_line(model),
            "models": self.pricing.model_options(),
            "spent_text": f"Spent today {money(spent)} of a {money(ceiling)} ceiling.",
            "on_message": self.on_message(),
            "spent_short": self.spent_short(),
        }

    def spent_short(self) -> str:
        return f"Today: {money(self.pricing.spent_today())}"

    def on_message(self) -> str:
        s = self.settings.all()
        if not s["enabled"]:
            return "Image and video reader off."
        mode = "Auto mode" if s["mode"] == "auto" else "Manual mode"
        text = f"Image and video reader on. {mode}, {short_name(s['model'])}."
        if s["readouts"]:
            text += f" Spent today {money(self.pricing.spent_today())} of {money(float(s['ceiling']))}."
        return text

    def apply_setting(self, key: str, value: Any) -> str:
        """Change one setting and return the sentence that confirms it, with its cost."""
        value = self.settings.set(key, value)
        model = self.settings.get("model")
        if key == "model":
            self._on_model_change(value)
            return f"Model set to {short_name(value)}. " + self.pricing.price_line(value)
        if key == "mode":
            if value == "auto":
                return (f"Auto mode on. Each image is described and each video narrated as you reach it, "
                        f"within your {money(float(self.settings.get('ceiling')))} daily ceiling.")
            return "Manual mode on. Nothing is sent until you ask."
        if key == "video_cap":
            return (f"Most to spend on one video set to {money(value)}." if value > 0
                    else "No limit for one video. Only the daily ceiling applies.")
        if key == "ceiling":
            self.guard.reset_ceiling_warning()
            return f"Daily ceiling set to {money(value)}. Spent today {money(self.pricing.spent_today())}."
        if key == "readouts":
            return "Cost readouts on." if value else "Cost readouts off. Prices are still read when you change the model."
        if key == "output":
            return {"screen_reader": "Output set to your screen reader.", "browser_voice": "Output set to the browser voice.",
                    "hermes_voice": "Output set to the Hermes voice."}[value]
        if key == "enabled":
            return self.on_message()
        if key == "chime":
            return "A sound plays when the outline moves." if value else "No sound when the outline moves."
        if key == "read_titles":
            return "Captions and titles will be read first." if value else "Captions and titles won't be read; your screen reader has them."
        if key == "replace_alt":
            return ("Images with alt text will be described too. Their own alt text is kept after the description."
                    if value else "Images that already have alt text are left as they are.")
        if key == "captions":
            return "Captions on screen on." if value else "Captions on screen off."
        if key == "setup_done":
            return "Setup finished."
        return f"{key} set to {value}."

    def _allowed(self, cost: float) -> tuple[bool, str]:
        return self.guard.check(cost)

    def _record(self, kind: str, tin: int, tout: int) -> tuple[float, str]:
        self.guard.note_call()
        cost = self.pricing.record(self.settings.get("model"), kind, tin, tout)
        return cost, self.guard.threshold_message()

    @staticmethod
    def _error_text(exc: Exception) -> str:
        busy = "429" in str(exc) or "rate" in str(exc).lower()
        return ("The model is busy right now. Try again in a moment, or pick another model in the reader's settings."
                if busy else "The description did not come through. Try again in a moment.")

    def describe_image(self, *, src: str = "", image_b64: str = "", alt: str = "", reason: str = "add") -> dict:
        alt = alt if reason == "improve" else ""
        key = f"{src}|{alt}" if src else ""
        if key and key in self._cache:
            return {"text": self._cache[key], "cached": True}
        ok, msg = self._allowed(self.pricing.image_cost(self.settings.get("model")))
        if not ok:
            return {"error": msg or "Paused by the spending guard."}
        raw = base64.b64decode(image_b64) if image_b64 else None
        jpeg = shrink(raw, IMAGE_MAX) if raw else None
        if not jpeg:
            return {"error": "Could not load that image."}
        try:
            text, tin, tout, _ = self.describer.image(jpeg, alt)
        except Exception as exc:
            logger.warning("blind-accessibility-reader: image failed: %s", exc)
            return {"error": self._error_text(exc)}
        _, warn = self._record("image", tin, tout)
        if key and text:
            self._cache[key] = text
        return {"text": text, "warning": warn, "spent": self.spent_short()}

    def video_offer(self, seconds: Optional[float]) -> str:
        """Only long videos and live streams get a spoken cost warning; short ones play in silence.
        The price of anything is always available on request with Alt+Shift+P."""
        if seconds and seconds < LONG_VIDEO_SECONDS:
            return ""
        low, high = self.pricing.video_range(self.settings.get("model"), seconds)
        if high <= 0 or not self.settings.get("readouts"):
            return ""
        if seconds:
            return f"This video is {_duration(seconds)}. Narrating all of it would cost {spoken_range(low, high)}."
        return f"This is a live stream. Narrating it costs {spoken_range(low, high)} an hour."

    def price_estimate(self, kind: str, seconds: Optional[float] = None) -> str:
        """What Alt+Shift+P says: the cost of describing, in plain spoken words."""
        model = self.settings.get("model")
        today = spoken(self.pricing.spent_today()).replace("about ", "")
        if kind == "video":
            low, high = self.pricing.video_range(model, seconds)
            cost = spoken_range(low, high)
            if seconds:
                return f"This video is {_duration(seconds)}. Narrating it would cost {cost}. Spent today: {today}."
            return f"Narrating this live stream would cost {cost} an hour. Spent today: {today}."
        img = self.pricing.image_cost(model)
        per_dollar = int(round(1 / img, -2)) if img > 0 else 0
        each = "is free" if img <= 0 else f"costs {spoken(img)}, so a dollar covers about {per_dollar:,} images"
        return f"Describing an image {each}. Spent today: {today}."

    def narration_start(self, video_key: str, seconds: Optional[float]) -> dict:
        low, high = self.pricing.video_range(self.settings.get("model"), seconds)
        cap = float(self.settings.get("video_cap") or 0)
        self._narrations[video_key] = {"budget": cap if cap > 0 else float("inf"), "spent": 0.0, "sig": None,
                                       "text": "", "live": False}
        return {"text": "Narrating."}

    def narration_stop(self, video_key: str) -> dict:
        self._narrations.pop(video_key, None)
        return {"text": "Narration off."}

    def frame(self, video_key: str, image_b64: str) -> dict:
        """One narration tick: returns text only when the scene really changed."""
        n = self._narrations.get(video_key)
        if n is None:
            return {"stop": True}
        shot = base64.b64decode(image_b64)
        sig = signature(shot)
        if sig is None:
            return {}
        if is_black(sig) and not n["text"]:
            self._narrations.pop(video_key, None)
            return {"text": BLACK_FRAME, "stop": True}
        if n["sig"] is not None and not changed(n["sig"], sig):
            return {}
        cost = self.pricing.frame_cost(self.settings.get("model"))
        if not n["live"] and n["spent"] + cost > n["budget"]:
            self._narrations.pop(video_key, None)
            return {"text": "Narration stopped: this video reached your limit for one video. Press Alt+Shift+D to keep going.", "stop": True}
        ok, msg = self._allowed(cost)
        if not ok:
            return {"text": msg, "stop": True} if msg else {"stop": True}
        n["sig"] = sig
        try:
            text, did_change, tin, tout, _ = self.describer.frame(shrink(shot, FRAME_WIDTH) or shot, n["text"])
        except Exception as exc:
            return {"text": self._error_text(exc)}
        spent, warn = self._record("frame", tin, tout)
        n["spent"] += spent
        if text and (did_change or not n["text"]):
            n["text"] = text
            self.recent.append((time.time(), text))
            return {"text": text, "warning": warn, "spent": self.spent_short()}
        return {"warning": warn, "spent": self.spent_short()}

    def single_frame(self, image_b64: str) -> dict:
        ok, msg = self._allowed(self.pricing.frame_cost(self.settings.get("model")))
        if not ok:
            return {"error": msg or "Paused by the spending guard."}
        shot = base64.b64decode(image_b64)
        if is_black(signature(shot)):
            return {"text": BLACK_FRAME}
        try:
            text, _c, tin, tout, _ = self.describer.frame(shrink(shot, FRAME_WIDTH) or shot, "")
        except Exception as exc:
            return {"error": self._error_text(exc)}
        _, warn = self._record("frame", tin, tout)
        self.recent.append((time.time(), text))
        return {"text": text, "warning": warn, "spent": self.spent_short()}

    def screen(self, image_b64: str, question: str = "") -> dict:
        ok, msg = self._allowed(self.pricing.image_cost(self.settings.get("model")))
        if not ok:
            return {"error": msg or "Paused by the spending guard."}
        jpeg = shrink(base64.b64decode(image_b64), IMAGE_MAX)
        if not jpeg:
            return {"error": "Could not capture the screen."}
        try:
            text, tin, tout, _ = self.describer.screen(jpeg, question)
        except Exception as exc:
            return {"error": self._error_text(exc)}
        _, warn = self._record("image", tin, tout)
        return {"text": text, "warning": warn}

    def speak(self, text: str) -> dict:
        raw = self._ctx.dispatch_tool("text_to_speech", {"text": text})
        try:
            path = json.loads(raw).get("file_path")
            data = Path(path).read_bytes()
        except Exception as exc:
            logger.info("blind-accessibility-reader: Hermes voice failed: %s", exc)
            return {"error": "The Hermes voice is not available. Check the voice settings in Hermes."}
        mime = "audio/ogg" if path.endswith(".ogg") else "audio/mpeg"
        return {"audio": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}

    def seen(self) -> None:
        self.last_seen = time.time()

    def tick(self) -> dict:
        self.last_seen = time.time()
        return {"command": self._pending.popleft() if self._pending else None}

    def extension_connected(self) -> bool:
        return time.time() - self.last_seen < 10

    def ask_extension(self, command: dict, timeout: float = 25) -> Optional[str]:
        command = dict(command, id=f"c{time.time_ns()}")
        self._pending.append(command)
        deadline = time.time() + timeout
        with self._result_event:
            while command["id"] not in self._results:
                left = deadline - time.time()
                if left <= 0:
                    return None
                self._result_event.wait(left)
            return self._results.pop(command["id"])

    def command_result(self, command_id: str, text: str) -> dict:
        with self._result_event:
            self._results[command_id] = text
            self._result_event.notify_all()
        return {}


def spoken(usd: float) -> str:
    """Money said out loud: no long strings of zeros."""
    if usd <= 0:
        return "nothing"
    if usd < 0.01:
        return "less than a cent"
    if usd < 1:
        c = round(usd * 100)
        return f"about {c} cent{'s' if c != 1 else ''}"
    return f"about {usd:.2f} dollars"


def spoken_range(low: float, high: float) -> str:
    a, b = spoken(low), spoken(high)
    if a == b:
        return a
    if a.endswith(" cents") and b.endswith(" cents"):
        return f"{a[:-6]} to {b.replace('about ', '')}"
    return f"{a} to {b.replace('about ', '')}"


def _duration(sec: float) -> str:
    if sec < 60:
        s = max(1, round(sec))
        return f"{s} second{'s' if s != 1 else ''}"
    h, m = int(sec // 3600), round((sec % 3600) / 60)
    if h and m:
        return f"{h} hour{'s' if h != 1 else ''} {m} minute{'s' if m != 1 else ''}"
    if h:
        return f"{h} hour{'s' if h != 1 else ''}"
    m = max(m, 1)
    return f"{m} minute{'s' if m != 1 else ''}"
