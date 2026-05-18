"""Parse cart management commands (show, remove, update)."""

from __future__ import annotations

import re

from app.domain.models import Product
from app.services.shopping_session import CartLine

_REMOVE_RE = re.compile(
    r"(?i)^(?:remove|delete)\s+(.+?)(?:\s+from\s+(?:the\s+)?cart)?\s*[.!?]?$"
)
_UPDATE_RE = re.compile(
    r"(?i)^(?:update|change|set|modify)\s+(.+?)\s+(?:qty|quantity|amount|weight)?\s*(?:to|=)\s+(.+?)\s*[.!?]?$"
)
_CLEAR_CART_RE = re.compile(r"(?i)^(?:clear\s+cart|empty\s+cart)$")


def wants_show_cart(text: str) -> bool:
    t = (text or "").strip().lower().rstrip(".!?,")
    return t in {"cart", "my cart", "show cart", "view cart", "see cart", "cart view"}


def wants_clear_cart(text: str) -> bool:
    return bool(_CLEAR_CART_RE.match((text or "").strip()))


def is_cart_management_command(text: str) -> bool:
    """Fast-path cart view / clear / remove (updates go through intent + cart context)."""
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(wants_show_cart(raw) or wants_clear_cart(raw) or parse_remove_target(raw))


def parse_remove_target(text: str) -> str | None:
    m = _REMOVE_RE.match((text or "").strip())
    return m.group(1).strip() if m else None


def parse_update_command(text: str) -> tuple[str, str] | None:
    m = _UPDATE_RE.match((text or "").strip())
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def pack_count_override_from_update_value(new_val: str) -> int | None:
    """Bare integer updates (e.g. ``to 2``) mean pack count, not grams."""
    raw = (new_val or "").strip()
    if raw.isdigit():
        n = int(raw)
        return n if n > 0 else None
    return None


def find_cart_line_index(cart: list[CartLine], query: str, products_by_sku: dict[str, Product]) -> int | None:
    q = (query or "").strip()
    if not q:
        return None
    qu = q.upper()
    ql = q.lower()

    for i, line in enumerate(cart):
        if line.sku.upper() == qu:
            return i

    for i, line in enumerate(cart):
        if ql in line.name.lower():
            return i

    for i, line in enumerate(cart):
        p = products_by_sku.get(line.sku)
        if not p:
            continue
        for word in re.findall(r"[a-z]{3,}", ql):
            if word in p.name.lower() or word in p.sku.lower():
                return i
    return None
