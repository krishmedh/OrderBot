"""Detect generic grocery chat without a specific product reference."""

from __future__ import annotations

import re

_VAGUE_BLOB_RE = re.compile(
    r"(?:^|\s)(?:"
    r"(?:need|want|get|would\s+like|looking\s+for|going\s+to\s+buy)"
    r".{0,60}?"
    r"(?:some|few|a\s+few|couple\s+of|little|lots?\s+of|various)?"
    r"\s*(?:items?|things|stuff)"
    r"|(?:some|few|those|these)\s+(?:items|things)"
    r"|\bhousehold\b"
    r"|\bgrocer(?:y|ies)\s+(?:for|shopping|shopping\s+trip)"
    r"|\bpantry\b.*\b(?:needs?|shopping|stuff)\b"
    r"|\b(?:general|usual)\s+shopping\b"
    r")",
    re.IGNORECASE | re.DOTALL,
)


def looks_like_open_ended_shopping_without_product(blob: str) -> bool:
    """Customer wants to shop but does not name a concrete SKU-level product."""
    raw = (blob or "").strip()
    return bool(raw) and bool(_VAGUE_BLOB_RE.search(raw))


GENERIC_GREETING_FILLER_PRODUCT_TOKENS: frozenset[str] = frozenset(
    {
        "items",
        "item",
        "things",
        "thing",
        "stuff",
        "household",
        "home",
        "necessities",
        "need",
        "needs",
        "essentials",
        "basics",
        "provision",
        "provisions",
        "supplies",
        "groceries",
        "grocery",
        "sundries",
        "pantry",
        "consumables",
    }
)


def extracted_keywords_are_only_generic_fillers(tokens: list[str]) -> bool:
    if not tokens:
        return False
    return frozenset(tokens) <= GENERIC_GREETING_FILLER_PRODUCT_TOKENS
