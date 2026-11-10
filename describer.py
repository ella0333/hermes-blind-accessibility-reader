"""Image preparation and vision model calls."""

from __future__ import annotations

import io
import logging
from typing import Any, Optional

logger = logging.getLogger("plugin.blind-accessibility-reader")
TASK = "visual_description"
IMAGE_MAX = 768
FRAME_WIDTH = 512
MAX_FETCH_BYTES = 15 * 1024 * 1024
IMAGE_PROMPT = (
    "Describe this image for someone who cannot see it, in one or two plain sentences. "
    "Lead with what matters most: any text in the image (quote it exactly), the people and what they are doing, "
    "or the point of a meme, chart or screenshot. Be concise and factual. Do not start with 'This image' or "
    "'The image', and do not mention that it is an image unless that matters.")
IMPROVE_PROMPT = (" The image already has this short alt text: \"{alt}\". Describe the image itself, adding the details "
                  "that alt text leaves out. Do not repeat, quote or comment on the alt text.")
PLAYER_RULE = (
    " Ignore the video player itself: timestamps, countdowns, progress bars, play and mute buttons, view counts, "
    "channel names and like buttons. Only read text that is part of the video, such as titles or captions burned "
    "into the picture.")
FRAME_PROMPT = (
    "This is a frame from a video someone is watching but cannot see. Previous narration: \"{previous}\". "
    "In one short sentence, say what is happening now, focusing on what changed in the scene." + PLAYER_RULE +
    " Set changed to false if nothing meaningful changed in the scene, for example if only a timer moved.")
FIRST_FRAME_PROMPT = (
    "This is a frame from a video someone is watching but cannot see. In one or two short sentences, say who "
    "or what is on screen and what is happening." + PLAYER_RULE)
SCREEN_PROMPT = (
    "This is a screenshot of the web page someone is looking at but cannot see. {question} "
    "Answer in a few plain sentences, leading with what matters most.")
BLACK_FRAME = "The video frame is black. Protected streaming services block screenshots, so this video cannot be described."
IMAGE_SCHEMA = {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]}
FRAME_SCHEMA = {"type": "object", "properties": {"description": {"type": "string"}, "changed": {"type": "boolean"}},
                "required": ["description", "changed"]}


def shrink(data: bytes, max_side: int = IMAGE_MAX) -> Optional[bytes]:
    """Resize to max_side on the long side and save as JPEG quality 80."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if getattr(img, "n_frames", 1) > 1:
            img.seek(max(0, img.n_frames // 3))
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception as exc:
        logger.info("blind-accessibility-reader: could not read image: %s", exc)
        return None


def signature(data: bytes) -> Optional[list[int]]:
    """Tiny grayscale thumbnail used to tell whether a video scene really changed."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("L").resize((32, 18))
        return list(img.getdata())
    except Exception:
        return None


def changed(a: Optional[list[int]], b: Optional[list[int]], threshold: float = 12.0) -> bool:
    if a is None or b is None or len(a) != len(b):
        return True
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a) > threshold


def is_black(sig: Optional[list[int]]) -> bool:
    return bool(sig) and max(sig) < 12


def fetch_image(url: str) -> Optional[bytes]:
    if not url.startswith(("http://", "https://")):
        return None
    try:
        import requests
        with requests.get(url, timeout=10, stream=True, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status_code != 200:
                return None
            data = resp.raw.read(MAX_FETCH_BYTES + 1, decode_content=True)
            return None if len(data) > MAX_FETCH_BYTES else data
    except Exception as exc:
        logger.info("blind-accessibility-reader: image fetch failed: %s", exc)
        return None


class Describer:
    def __init__(self, ctx: Any):
        self._ctx = ctx

    def _call(self, prompt: str, jpeg: bytes, schema: dict, max_tokens: int = 200) -> tuple[dict, int, int, str]:
        result = self._ctx.llm.complete_structured(
            instructions=prompt,
            input=[{"type": "image", "data": jpeg, "mime_type": "image/jpeg"}],
            json_schema=schema, schema_name="description",
            temperature=0.1, max_tokens=max_tokens, task=TASK, purpose="image description")
        parsed = result.parsed if isinstance(result.parsed, dict) else {"description": (result.text or "").strip(), "changed": True}
        return parsed, result.usage.input_tokens, result.usage.output_tokens, result.model

    def image(self, jpeg: bytes, original_alt: str = "") -> tuple[str, int, int, str]:
        prompt = IMAGE_PROMPT + (IMPROVE_PROMPT.format(alt=original_alt[:300]) if original_alt else "")
        parsed, tin, tout, model = self._call(prompt, jpeg, IMAGE_SCHEMA)
        return str(parsed.get("description", "")).strip(), tin, tout, model

    def frame(self, jpeg: bytes, previous: str = "") -> tuple[str, bool, int, int, str]:
        prompt = FRAME_PROMPT.format(previous=previous[:300]) if previous else FIRST_FRAME_PROMPT
        parsed, tin, tout, model = self._call(prompt, jpeg, FRAME_SCHEMA, max_tokens=120)
        return str(parsed.get("description", "")).strip(), bool(parsed.get("changed", True)), tin, tout, model

    def screen(self, jpeg: bytes, question: str = "") -> tuple[str, int, int, str]:
        q = f"They asked: \"{question[:300]}\"" if question else "Describe what is on the screen."
        parsed, tin, tout, model = self._call(SCREEN_PROMPT.format(question=q), jpeg, IMAGE_SCHEMA, max_tokens=300)
        return str(parsed.get("description", "")).strip(), tin, tout, model
