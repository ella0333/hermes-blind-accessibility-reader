"""Decides whether an image's alt text is missing, weak or good."""

from __future__ import annotations

import re

JUNK_ALT = re.compile(
    r"^(image|img|photo|picture|graphic|figure|thumbnail|media|gif|video|embedded video|untitled|"
    r"unknown|placeholder|loading)\b[\s\d.]*$", re.IGNORECASE)
FILE_ALT = re.compile(r"\.(jpe?g|png|gif|webp|avif|bmp|svg)(\?.*)?$", re.IGNORECASE)
HASH_ALT = re.compile(r"^[\w-]{20,}$")
REDDIT_TITLE_ALT = re.compile(r"^r/\w+ - ")


def judge(alt: str | None, *, role: str = "") -> str:
    """Return missing, weak, good or decorative for an image's alt text (None means no alt attribute)."""
    if alt is None:
        return "missing"
    text = alt.strip()
    if not text:
        return "decorative" if role == "presentation" else "missing"
    if JUNK_ALT.match(text) or FILE_ALT.search(text) or HASH_ALT.match(text):
        return "missing"
    if REDDIT_TITLE_ALT.match(text):
        return "weak"
    if len(text.split()) <= 3:
        return "weak"
    return "good"
