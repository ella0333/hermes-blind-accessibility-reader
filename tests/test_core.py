"""Offline tests: alt text judge, frame change check, pricing, ledger and spending guard. No model calls."""

import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_package():
    spec = importlib.util.spec_from_file_location("bavir", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["bavir"] = pkg
    spec.loader.exec_module(pkg)
    return pkg


_load_package()
from bavir.alt_judge import judge  # noqa: E402
from bavir.describer import changed, is_black, shrink, signature  # noqa: E402
from bavir.pricing import Pricing, money  # noqa: E402
from bavir.settings import Guard, Settings  # noqa: E402


class FakeState:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class FakeCtx:
    def __init__(self):
        self.state = FakeState()
        self.config = {}

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value


def _pricing():
    return Pricing(FakeCtx(), fetch=lambda: {"data": [
        {"id": "google/gemini-3.1-flash-lite", "pricing": {"prompt": "0.00000025", "completion": "0.0000015"}},
        {"id": "qwen/qwen3.7-flash", "pricing": {"prompt": "0.00000003", "completion": "0.00000013"}},
        {"id": "google/gemini-3.5-flash", "pricing": {"prompt": "0.0000015", "completion": "0.000009"}},
    ]})


def _jpeg(color, size=(640, 360)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def test_alt_judge():
    assert judge(None) == "missing"
    assert judge("") == "missing"
    assert judge("", role="presentation") == "decorative"
    assert judge("Image") == "missing"
    assert judge("IMG_2041.jpg") == "missing"
    assert judge("a8f3c9d2e1b7f6a5c4d3e2") == "missing"
    assert judge("r/funny - when the cat sees the vet") == "weak"
    assert judge("a cat") == "weak"
    assert judge("A grey cat asleep on a stack of library books") == "good"


def test_shrink_and_frames():
    big = _jpeg((200, 30, 30), (2000, 1000))
    from PIL import Image
    small = Image.open(io.BytesIO(shrink(big, 768)))
    assert max(small.size) == 768
    red, blue = signature(_jpeg((200, 30, 30))), signature(_jpeg((30, 30, 200)))
    assert not changed(red, signature(_jpeg((202, 31, 29))))
    assert changed(red, blue)
    assert is_black(signature(_jpeg((0, 0, 0))))
    assert not is_black(red)


def test_prices_and_readable_lines():
    p = _pricing()
    img = p.image_cost("google/gemini-3.1-flash-lite")
    assert abs(img - (1250 * 0.25e-6 + 60 * 1.5e-6)) < 1e-12  # measured Gemini image tokens
    assert abs(p.image_cost("qwen/qwen3.7-flash") - (450 * 0.03e-6 + 60 * 0.13e-6)) < 1e-12
    low, high = p.hour_range("google/gemini-3.1-flash-lite")
    assert 0.13 < low < 0.15 and 0.44 < high < 0.48
    assert p.is_expensive("google/gemini-3.5-flash")
    assert not p.is_expensive("qwen/qwen3.7-flash")
    line = p.price_line("google/gemini-3.1-flash-lite")
    assert "1 dollar covers about 2,500 images" in line and "0.14 dollars to 0.47 dollars" in line
    assert money(0.0004) == "0.0004 dollars" and money(1.42) == "1.42 dollars" and money(0.24) == "0.24 dollars"
    lo, hi = p.video_range("google/gemini-3.1-flash-lite", 3840)
    assert 0.14 < lo < 0.16 and 0.48 < hi < 0.51


def test_real_averages_replace_estimates_after_20_calls():
    p = _pricing()
    for _ in range(20):
        p.record("google/gemini-3.1-flash-lite", "image", 300, 40)
    assert abs(p.image_cost("google/gemini-3.1-flash-lite") - (300 * 0.25e-6 + 40 * 1.5e-6)) < 1e-12
    assert p.spent_today() > 0


def test_guard_ceiling_and_minute_cap():
    ctx = FakeCtx()
    settings = Settings(ctx)
    p = Pricing(ctx, fetch=lambda: {"data": []})
    guard = Guard(settings, p)
    settings.set("ceiling", 0.001)
    ok, msg = guard.check(0.0002)
    assert ok and msg == ""
    p.record("google/gemini-3.1-flash-lite", "image", 4000, 0)  # 0.1 cents spent
    ok, msg = guard.check(0.0002)
    assert not ok and "ceiling" in msg
    ok, msg = guard.check(0.0002)
    assert not ok and msg == ""  # said once, not again
    assert guard.check(0.0)[0]  # free models are never blocked by the ceiling
    settings.set("ceiling", 1.0)
    settings.set("per_minute", 2)
    guard.note_call()
    guard.note_call()
    ok, msg = guard.check(0.0002)
    assert not ok and "this minute" in msg


def test_model_setting_uses_unreserved_key():
    ctx = FakeCtx()
    Settings(ctx).set("model", "qwen/qwen3.7-flash")
    assert ctx.config == {"vision_model": "qwen/qwen3.7-flash"}


if __name__ == "__main__":
    # Run with: python tests/test_core.py (pytest would import the plugin folder's own __init__.py as a package)
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"{len(tests)} passed")
