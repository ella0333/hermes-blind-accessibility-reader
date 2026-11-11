"""Tool descriptions for the Hermes agent."""
DESCRIBE_VIEW = {
    "name": "describe_view",
    "description": (
        "Describe what is currently on screen in the person's connected browser tab, for a blind or low vision "
        "person. Use when they ask what is on their screen, what an image, chart or post shows, or what is "
        "happening in a video. Call it directly; no skill needs loading first. Pass their question so the answer focuses on it. Each call costs a small "
        "amount on their vision model and counts toward their daily ceiling."),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "What the person wants to know, in their words."},
        },
        "required": [],
    },
}
READER_SETTINGS = {
    "name": "reader_settings",
    "description": (
        "Read or change the Blind Accessibility Video and Image Reader settings when the person asks, for "
        "example 'turn on auto mode', 'switch to the cheapest model', 'how much have I spent today'. "
        "Always read the returned message back to them, since it includes the cost. Settings: mode (manual or auto), readouts (true or false, cost read in every prompt), output "
        "(screen_reader, browser_voice or hermes_voice), model (an OpenRouter model id from the get action), "
        "ceiling (daily dollars, can only be lowered here). Turning the reader on, raising the ceiling and "
        "switching to an expensive model are left to the person, in the settings panel or with /describe."),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get", "set"]},
            "setting": {"type": "string", "enum": ["mode", "readouts", "output", "model", "ceiling"]},
            "value": {"description": "New value for the setting."},
        },
        "required": ["action"],
    },
}
