"""Prompt helpers (cart state formatting for optional debug; not sent to classifier)."""

from __future__ import annotations

import re

from app.config import settings
from app.services.shopping_session import CartLine, cart_line_amount

_INCREMENT_RE = re.compile(
    r"(?i)\b(?:add\s+)?(?:one\s+more|another|extra|1\s+more|one\s+extra)\b"
)


def looks_like_cart_increment(*texts: str) -> bool:
    for raw in texts:
        t = (raw or "").strip()
        if t and _INCREMENT_RE.search(t):
            return True
    return False


def format_cart_state_for_prompt(cart: list[CartLine], *, currency: str | None = None) -> str:
    """Numbered cart lines (optional logging; not included in classifier prompt)."""
    cur = currency or settings.default_currency
    if not cart:
        return "(cart is empty)"

    rows: list[str] = []
    for i, line in enumerate(cart, start=1):
        amt = cart_line_amount(line)
        extra = f" — {line.weight_note}" if line.weight_note else ""
        rows.append(
            f"{i}. {line.name} (SKU: {line.sku}) qty_packs={line.quantity}{extra} "
            f"line_total={amt:.2f} {cur}"
        )
    total = sum(cart_line_amount(line) for line in cart)
    rows.append(f"Cart total: {total:.2f} {cur}")
    return "\n".join(rows)
