"""Parse delivery and payment replies during WhatsApp checkout."""

from __future__ import annotations

import re

_PHONE_RE = re.compile(
    r"(?:\+91[\s\-]?)?(?:91[\s\-]?)?([6-9]\d{9})\b|(?<!\d)([6-9]\d{9})(?!\d)"
)

_COD_RE = re.compile(
    r"\b(cod|cash\s*on\s*delivery|cash|pay\s*on\s*delivery|delivery\s*pe|pay\s*later)\b",
    re.I,
)
_ONLINE_RE = re.compile(
    r"\b(online|upi|razorpay|card|pay\s*online|payment\s*link|pay\s*now|link)\b",
    re.I,
)


def parse_delivery_details(text: str) -> tuple[str, str] | None:
    """Return (address, contact_phone) or None if message lacks both."""
    raw = (text or "").strip()
    if not raw:
        return None

    last_match: re.Match[str] | None = None
    for m in _PHONE_RE.finditer(raw):
        last_match = m
    if not last_match:
        return None

    digits = last_match.group(1) or last_match.group(2)
    contact = f"+91{digits}"

    address = (raw[: last_match.start()] + raw[last_match.end() :]).strip()
    address = re.sub(r"[\s,;|]+", " ", address).strip(" ,.-")
    if len(address) < 8:
        return None
    return address, contact


def parse_checkout_payment_method(text: str) -> str | None:
    """Return 'cod', 'online', or None."""
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    if low in ("1", "cod", "cash"):
        return "cod"
    if low in ("2", "online", "upi"):
        return "online"
    if _COD_RE.search(t) and not _ONLINE_RE.search(t):
        return "cod"
    if _ONLINE_RE.search(t) and not _COD_RE.search(t):
        return "online"
    if _COD_RE.search(t):
        return "cod"
    if _ONLINE_RE.search(t):
        return "online"
    return None
