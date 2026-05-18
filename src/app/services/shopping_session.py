"""Per-customer shopping cart and pending confirmations (same process memory as conversation)."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from app.domain.models import Product
from app.services.conversation_memory import conversation_memory_key


@dataclass
class CartLine:
    sku: str
    quantity: int  # catalogue packs to deduct from stock
    name: str
    unit_price: float
    line_total: float | None = None  # weight-scaled total; default unit_price * quantity
    weight_note: str = ""


@dataclass
class PendingSingle:
    sku: str
    name: str
    unit_price: float
    quantity: int = 1
    source_text: str = ""


@dataclass
class PendingCheckout:
    step: str  # "delivery" | "payment"
    delivery_address: str = ""
    contact_phone: str = ""


@dataclass
class ShoppingSession:
    cart: list[CartLine] = field(default_factory=list)
    pending_single: PendingSingle | None = None
    pending_options: list[Product] | None = None
    pending_quantity_batch: object | None = None
    pending_checkout: PendingCheckout | None = None


class ShoppingSessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, ShoppingSession] = {}

    def session(self, phone: str, store_id: str) -> ShoppingSession:
        key = conversation_memory_key(phone, store_id)
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = ShoppingSession()
            return self._sessions[key]

    def clear_pending(self, phone: str, store_id: str) -> None:
        key = conversation_memory_key(phone, store_id)
        with self._lock:
            s = self._sessions.get(key)
            if s:
                s.pending_single = None
                s.pending_options = None
                s.pending_quantity_batch = None


# "two mustard", "three packets of rice"
_WORD_NUMBERS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "pair": 2,
    "couple": 2,
}

_QTY_X = re.compile(r"(?i)\b(\d{1,3})\s*(?:x|×)\s+")
_QTY_PACK_WORD = re.compile(
    r"(?i)\b(\d{1,3})\s*(?:packets?|packs?|bottles?|pcs?|pieces?|units?|nos\.?)(?:\s+of)?\b"
)
# Pack count before a separate size word: "5 kg sugar" → 5 packs (not "200g" → 200).
_PACK_BEFORE_SIZE = re.compile(
    r"(?i)\b(\d{1,3})\s+(?=(?:\d+(?:\.\d+)?)?(?:kg|kgs|kilograms?|g|grams?|ml|l|liters?|litres?|ltr)\b)"
)
_QTY_AFTER_VERB = re.compile(
    r"(?i)\b(?:get|give|send|add|want|need|fetch|bring|order)(?:\s+(?:me|us))?\s+(\d{1,3})(?=\s+(?!(?:kg|kgs|g|grams?|ml|l|liters?|litres?|ltr)\b)\S)"
)
# "2 mustard 1 litre" → 2 packs; exclude "1 kg" / "1 litre" as the first token (size, not line qty).
_LEADING_PACK_DIGIT = re.compile(
    r"(?i)^\s*(\d{1,3})\s+(?!(?:kg|kgs|kilograms?|g|grams?|ml|l|liter|litre|ltr)s?\b)(?=\S)"
)
_LEADING_PACK_WORD = re.compile(
    r"(?i)^\s*(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|pair|couple)\s+"
    r"(?!(?:kg|kgs|kilograms?|g|grams?|ml|l|liter|litre|ltr)s?\b)(?=\S)"
)


def parse_quantity_from_text(text: str, default: int = 1) -> int:
    """Best-effort pack / order quantity from free text (e.g. ``2 mustard 1 litre`` → ``2``)."""
    raw = (text or "").strip()
    if not raw:
        return default

    if re.fullmatch(r"\d{1,3}", raw):
        return max(1, min(999, int(raw)))

    if m := _QTY_X.search(raw):
        return max(1, min(999, int(m.group(1))))

    if m := _QTY_PACK_WORD.search(raw):
        return max(1, min(999, int(m.group(1))))

    if m := _LEADING_PACK_DIGIT.match(raw):
        return max(1, min(999, int(m.group(1))))

    if m := _LEADING_PACK_WORD.match(raw):
        w = m.group(1).lower()
        if w in _WORD_NUMBERS:
            return max(1, min(999, _WORD_NUMBERS[w]))

    if m := _QTY_AFTER_VERB.search(raw):
        return max(1, min(999, int(m.group(1))))

    if m := _PACK_BEFORE_SIZE.search(raw):
        return max(1, min(999, int(m.group(1))))

    # Attached sizes (200g, 1kg glued) are product size, not pack count.
    return default


_CART_YES = re.compile(
    r"(?i)^(yes|yeah|yep|y|ok|okay|haan)(\s+(please|thanks|thank\s+you|sir|madam))?\s*[.!?]?$"
)


def parse_shopping_confirmation(text: str) -> tuple[bool, int | None]:
    """Whether this message confirms a pending offer; optional explicit quantity (``yes 3``)."""
    t = (text or "").strip().rstrip(".!?,")
    if not t:
        return False, None
    if _CART_YES.match(t):
        return True, None
    m = re.match(r"(?i)^(yes|yeah|yep|ok|okay|haan)\s+(\d{1,3})\s*$", t)
    if m:
        return True, max(1, min(999, int(m.group(2))))
    return False, None


def is_cart_confirmation_message(text: str) -> bool:
    return parse_shopping_confirmation(text)[0]


_AFFIRM = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "y",
        "ok",
        "okay",
        "sure",
        "confirm",
        "haan",
        "ha",
        "theek",
        "please",
    }
)


def is_affirmative_reply(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[.!?,]+$", "", t)
    if not t:
        return False
    first = t.split()[0]
    if first in _AFFIRM:
        return True
    return t.startswith("yes ") or t.startswith("ok ")


def is_negative_reply(text: str) -> bool:
    t = (text or "").strip().lower().rstrip(".!?,")
    return t in {"no", "nope", "nah", "cancel", "stop", "not now"}


_CHECKOUT_RE = re.compile(
    r"(?i)\b(checkout|check\s*out|place\s+my\s+order|confirm\s+order|pay\s+now|finish\s+order|done\s+shopping)\b"
)


def wants_cart_checkout(text: str) -> bool:
    return bool(_CHECKOUT_RE.search(text or ""))


_OIL_WORD = re.compile(r"\boils?\b", re.IGNORECASE)


def user_asked_about_oil(text: str) -> bool:
    return bool(_OIL_WORD.search(text or ""))


def filter_oil_products(products: list[Product]) -> list[Product]:
    return [p for p in products if "oil" in p.name.lower() or "oil" in p.sku.lower()]


_GENERIC_SKIP = frozenset(
    {"oil", "the", "and", "for", "with", "litre", "liter", "litres", "liters", "ltr", "get", "want", "give", "me"}
)


def pick_product_from_message(message: str, candidates: list[Product]) -> Product | None:
    """Pick one product from a short list using fuzzy name matching."""
    from app.services.catalog_fuzzy import score_product_match
    from app.services.inventory_service import extract_product_keywords

    if not candidates:
        return None
    msg = (message or "").strip()
    tokens = extract_product_keywords(msg)
    best_score = 0.0
    best: Product | None = None
    for p in candidates:
        s = score_product_match(p, msg, product_tokens=tokens)
        if s > best_score:
            best_score = s
            best = p
    if best_score < 50.0:
        return None
    # Clear winner among close candidates
    second = 0.0
    for p in candidates:
        if p is best:
            continue
        second = max(second, score_product_match(p, msg, product_tokens=tokens))
    if second >= best_score - 8.0:
        return None
    return best


def cart_line_amount(line: CartLine) -> float:
    if line.line_total is not None:
        return line.line_total
    return line.unit_price * line.quantity


def cart_total_inr(lines: list[CartLine]) -> float:
    return sum(cart_line_amount(line) for line in lines)
