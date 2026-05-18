"""Detect catalogue menu requests (shared by Meta inbound and orchestrator)."""

from __future__ import annotations

import re

# Exact / short menu commands (whole message).
_MENU_CMD = re.compile(
    r"^(?:"
    r"menu\s+please|please\s+menu|"
    r"(?:please\s+)?menu(?:\s+\d+)?|"
    r"show\s+(?:me\s+)?(?:the\s+)?menu(?:\s+please)?|"
    r"(?:please\s+)?(?:show|send|give)\s+(?:me\s+)?(?:the\s+)?(?:product\s+)?(?:catalog(?:ue)?|items)|"
    r"items|products|catalogue|catalog|list"
    r")\s*[.!?]?$",
    re.IGNORECASE,
)
_MENU_PAGE = re.compile(r"\bpage\s*(\d+)\b|\bmenu\s+(\d+)\b", re.IGNORECASE)

# Normalized LLM phrasing or longer polite asks still mean “show the catalogue”.
_MENU_PHRASE = re.compile(
    r"(?i)(?:"
    r"(?:show|send|see|view|get|display)\s+(?:me\s+)?(?:the\s+)?(?:store\s+)?menu"
    r"|(?:show|send)\s+(?:me\s+)?(?:the\s+)?(?:product\s+)?(?:catalog(?:ue)?|item\s+list)"
    r"|\bmenu\b.*\b(?:please|pls)\b"
    r"|\b(?:please|pls)\b.*\bmenu\b"
    r")"
)


def is_menu_command(text: str) -> bool:
    return looks_like_menu_request(text)


def looks_like_menu_request(text: str) -> bool:
    """True when the customer wants the product catalogue / menu (not a food item named menu)."""
    raw = (text or "").strip()
    if not raw:
        return False
    if _MENU_CMD.match(raw):
        return True
    if _MENU_PHRASE.search(raw):
        return True
    return False


def menu_page_index(text: str) -> int:
    raw = (text or "").strip().lower()
    m = _MENU_PAGE.search(raw)
    if m:
        p = m.group(1) or m.group(2)
        return max(0, int(p) - 1)
    return 0
