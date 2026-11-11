"""Blind Accessibility Video and Image Reader: Hermes plugin entry point."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

from . import schemas
from .describer import TASK
from .pricing import Pricing, cost_text, money, short_name
from .server import DEFAULT_PORT, LocalServer
from .service import Service
from .settings import Settings

logger = logging.getLogger("plugin.blind-accessibility-reader")
__version__ = "0.2.0"

_service: Optional[Service] = None
_server: Optional[LocalServer] = None
_ctx: Any = None
EXTENSION_DIR = Path(__file__).parent / "extension"
CEILING_CHOICES = [("0.25", "0.25 dollars a day"), ("0.5", "0.50 dollars a day"), ("1", "1 dollar a day"),
                   ("2", "2 dollars a day")]
OUTPUT_CHOICES = [("screen_reader", "My screen reader"), ("browser_voice", "The browser voice, free"),
                  ("hermes_voice", "The Hermes voice")]
OPENROUTER_LIMIT_TIP = "Tip: add an additional spending limit to your OpenRouter key at openrouter.ai."
AGENT_SETTINGS = ("mode", "readouts", "output", "model", "ceiling")


def _extension_steps() -> str:
    return ("To add the browser extension, which you only do once: open chrome://extensions in Chrome, turn on "
            "Developer mode, choose Load unpacked, and pick this folder:\n"
            f"{EXTENSION_DIR}\n"
            "After that, Alt+Shift+S opens the reader's settings in any tab and Alt+Shift+D describes.")


def _aux_defaults(model: str) -> dict[str, Any]:
    return {"provider": "openrouter", "model": model, "extra_body": {"reasoning": {"enabled": False}}}


def _register_model(model: str) -> None:
    _ctx.register_auxiliary_task(
        TASK, display_name="Image and video descriptions",
        description="Vision model the Blind Accessibility Video and Image Reader uses to describe images and video frames.",
        defaults=_aux_defaults(model))


def _start_server() -> str:
    return _server.start() if _server else ""


def _status() -> str:
    s = _service.settings.all()
    connected = "connected" if _service.extension_connected() else "not connected right now"
    return "\n".join([
        f"The image and video reader is {'on' if s['enabled'] else 'off'}. The browser extension is {connected}.",
        f"Mode: {s['mode']}. Output: {s['output'].replace('_', ' ')}. Cost readouts: {'on' if s['readouts'] else 'off'}.",
        _service.pricing.price_line(s["model"]),
        f"Spent today: {money(_service.pricing.spent_today())} of a {money(float(s['ceiling']))} daily ceiling.",
    ])


def _model_choices() -> list[dict[str, str]]:
    return [{"value": m["id"], "label": m["label"]} for m in _service.pricing.model_options()]


def _choose_model() -> Optional[str]:
    picked = _ctx.ask_choice("Which model should describe images and video? Prices are listed with each.", _model_choices())
    if not picked:
        return None
    if _service.pricing.is_expensive(picked):
        high = _service.pricing.hour_range(picked)[1]
        ok = _ctx.ask_choice(f"{short_name(picked)} costs up to {money(high)} for an hour of busy video. Switch to it?",
                             [{"value": "yes", "label": "Yes, switch"}, {"value": "no", "label": "No, keep the current model"}])
        if ok != "yes":
            return None
    return picked


def _setup() -> str:
    model = _choose_model() or _service.settings.get("model")
    _service.apply_setting("model", model)
    ceiling = _ctx.ask_choice("How much can it spend each day at most?",
                              [{"value": v, "label": l} for v, l in CEILING_CHOICES]) or "0.5"
    _service.apply_setting("ceiling", float(ceiling))
    readouts = _ctx.ask_choice("Should every describe button and video prompt read its price?",
                               [{"value": "yes", "label": "Yes, read the price every time"},
                                {"value": "no", "label": "No, only when I change the model"}]) or "yes"
    _service.apply_setting("readouts", readouts == "yes")
    img = cost_text(_service.pricing.image_cost(model))
    mode = _ctx.ask_choice("Should images with no alt text be described automatically?",
                           [{"value": "manual", "label": "No, only when I press describe"},
                            {"value": "auto", "label": f"Yes, as I browse, {img} each"}]) or "manual"
    _service.apply_setting("mode", mode)
    output = _ctx.ask_choice("Where should descriptions be read?", [{"value": v, "label": l} for v, l in OUTPUT_CHOICES]) \
        or "screen_reader"
    _service.apply_setting("output", output)
    _service.apply_setting("enabled", True)
    _service.settings.set("setup_done", True)
    return "All set.\n" + _status() + "\n" + OPENROUTER_LIMIT_TIP + "\n" + _extension_steps()


def _command(raw_args: str = "", **_: Any) -> str:
    _start_server()
    args = (raw_args or "").strip().split()
    word = args[0].lower() if args else ""
    rest = args[1:]
    enabled = _service.settings.get("enabled")
    try:
        if not word:
            word = _ctx.ask_choice("What would you like to do?", [
                {"value": "off" if enabled else "on", "label": "Turn describing " + ("off" if enabled else "on")},
                {"value": "status", "label": "Hear the status and today's spending"},
                {"value": "settings", "label": "Change a setting"},
                {"value": "price", "label": "Hear what a dollar buys"},
                {"value": "extension", "label": "How to add the browser extension"}]) or "status"
        if word == "on":
            if not _service.settings.get("setup_done"):
                return _setup()
            return _service.apply_setting("enabled", True)
        if word == "off":
            return _service.apply_setting("enabled", False)
        if word == "status":
            return _status()
        if word == "price":
            return _service.pricing.price_line(_service.settings.get("model"))
        if word == "setup":
            return _setup()
        if word == "extension":
            return _extension_steps()
        if word == "settings":
            word = _ctx.ask_choice("Which setting?", [
                {"value": "mode", "label": "Manual or auto"}, {"value": "readouts", "label": "Price readouts"},
                {"value": "model", "label": "Model"}, {"value": "ceiling", "label": "Daily ceiling"},
                {"value": "output", "label": "Where descriptions are read"}]) or "status"
            if word == "mode":
                word = _ctx.ask_choice("Manual or auto?", [{"value": "manual", "label": "Manual"}, {"value": "auto", "label": "Auto"}]) or "status"
            if word == "status":
                return _status()
        if word == "manual":
            return _service.apply_setting("mode", "manual")
        if word == "auto":
            img = cost_text(_service.pricing.image_cost(_service.settings.get("model")))
            ceiling = money(float(_service.settings.get("ceiling")))
            ok = _ctx.ask_choice(f"Auto describes every image with no alt text as you browse, {img} each. "
                                 f"Your daily ceiling is {ceiling}. Turn it on?",
                                 [{"value": "yes", "label": "Yes, turn auto on"}, {"value": "no", "label": "No, stay manual"}])
            if ok != "yes" and ok is not None:
                return "Staying in manual mode."
            return _service.apply_setting("mode", "auto")
        if word == "model":
            picked = rest[0] if rest else _choose_model()
            if not picked:
                return "Model unchanged. " + _service.pricing.price_line(_service.settings.get("model"))
            return _service.apply_setting("model", picked)
        if word == "ceiling":
            value = rest[0] if rest else _ctx.ask_choice("Daily ceiling?", [{"value": v, "label": l} for v, l in CEILING_CHOICES])
            return _service.apply_setting("ceiling", float(str(value).lstrip("$"))) if value else _status()
        if word == "readouts":
            value = rest[0].lower() if rest else _ctx.ask_choice("Price readouts?", [{"value": "on", "label": "On"}, {"value": "off", "label": "Off"}])
            return _service.apply_setting("readouts", value == "on") if value else _status()
        if word == "output":
            value = rest[0] if rest else _ctx.ask_choice("Where should descriptions be read?", [{"value": v, "label": l} for v, l in OUTPUT_CHOICES])
            return _service.apply_setting("output", value) if value else _status()
    except (ValueError, KeyError) as exc:
        return f"That did not work: {exc}"
    return "Type /describe on its own for a menu, or /describe followed by on, off, status, price, setup or extension."


def _tool_describe_view(args: dict, **_: Any) -> str:
    _start_server()
    if not _service.extension_connected():
        return json.dumps({"error": "The browser extension isn't connected. Open Chrome with the reader extension "
                                    "added, then ask again. " + _extension_steps()})
    text = _service.ask_extension({"kind": "screen", "question": str(args.get("question", ""))})
    return json.dumps({"description": text} if text else {"error": "The browser didn't answer in time. Try again."})


def _tool_settings(args: dict, **_: Any) -> str:
    try:
        if args.get("action", "get") == "get":
            return json.dumps({"status": _status(), "models": _service.pricing.model_options()})
        key, value = str(args.get("setting")), args.get("value")
        if key not in AGENT_SETTINGS:
            return json.dumps({"error": "That setting can only be changed by the person, in the settings panel "
                                        "with Alt+Shift+S or with /describe."})
        if key == "ceiling" and float(value) > float(_service.settings.get("ceiling")):
            return json.dumps({"error": "The daily ceiling can only be raised by the person, in the settings panel "
                                        "with Alt+Shift+S or with /describe setup."})
        if key == "model" and _service.pricing.is_expensive(str(value)):
            high = _service.pricing.hour_range(str(value))[1]
            return json.dumps({"error": f"{short_name(str(value))} costs up to {money(high)} per hour of busy video, "
                                        "so the person has to switch to it themselves with /describe model."})
        return json.dumps({"message": _service.apply_setting(key, value)})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _on_session_start(**_: Any) -> None:
    _start_server()


def _pre_llm_call(**_: Any) -> Optional[dict]:
    if not _service:
        return None
    recent = [t for at, t in _service.recent if time.time() - at < 600]
    if not recent:
        return None
    return {"context": "Recent narration of the video the person is watching:\n" + "\n".join(recent[-5:])}


def _cli_setup(parser: Any) -> None:
    parser.add_argument("words", nargs="*", help="start, status, price, extension, manual, auto, model <id>, "
                                                 "ceiling <dollars>, readouts on|off, output <name>")


def _cli_handler(ns: Any) -> None:
    words = list(getattr(ns, "words", []) or [])
    first = words[0] if words else "status"
    if first == "start":
        problem = _start_server()
        if problem:
            print(problem)
            return
        print(_service.on_message())
        print("The browser extension can connect now. Leave this window open while you browse; close it to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            _server.stop()
            print("Image and video reader stopped.")
        return
    if first == "status":
        print(_status())
    elif first == "price":
        print(_service.pricing.price_line(_service.settings.get("model")))
    elif first == "extension":
        print(_extension_steps())
    elif first in ("manual", "auto"):
        print(_service.apply_setting("mode", first))
    elif len(words) >= 2 and first in ("model", "ceiling", "output"):
        print(_service.apply_setting(first, float(words[1]) if first == "ceiling" else words[1]))
    elif len(words) >= 2 and first == "readouts":
        print(_service.apply_setting("readouts", words[1].lower() == "on"))
    else:
        print("Use: hermes describe start, status, price, extension, manual, auto, model <id>, ceiling <dollars>, "
              "readouts on|off, output <name>.")


def register(ctx: Any) -> None:
    global _service, _server, _ctx
    _ctx = ctx
    settings = Settings(ctx)
    pricing = Pricing(ctx)
    _register_model(settings.get("model"))
    _service = Service(ctx, settings, pricing, on_model_change=_register_model)
    _server = LocalServer(_service, DEFAULT_PORT)

    ctx.register_command("describe", _command,
                         description="Image and video descriptions for blind and low vision people: settings, prices, setup",
                         args_hint="[on|off|status|price|setup|extension|manual|auto|model|ceiling|readouts|output]")
    ctx.register_cli_command("describe", "Blind Accessibility Video and Image Reader: start, settings and prices",
                             _cli_setup, _cli_handler)
    ctx.register_tool(name="describe_view", toolset="blind-accessibility-reader", schema=schemas.DESCRIBE_VIEW,
                      handler=_tool_describe_view)
    ctx.register_tool(name="reader_settings", toolset="blind-accessibility-reader", schema=schemas.READER_SETTINGS,
                      handler=_tool_settings)
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.on_unload(lambda: _server.stop() if _server else None)

    if "gateway" in sys.argv and "run" in sys.argv:
        _start_server()

