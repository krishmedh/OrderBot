"""Parse and pair multiple grocery line items for bulk add-to-cart."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.intent_classification import IntentEntities

# Comma or semicolon between distinct product clauses (not thousands separators).
_CLAUSE_SPLIT = re.compile(r"\s*[,;]\s*")

_SIZE_UNITS = (
    r"kg|kgs|kilograms?|g|grams?|gm|gms|mg|ml|l|liters?|litres?|ltr|"
    r"m|metres?|meters?|"
    r"packets?|packs?|bottles?|pcs?|pieces?|units?|nos\.?"
)
_SIZE_IN_TEXT = re.compile(
    rf"(\d+(?:\.\d+)?)\s*({_SIZE_UNITS})\b",
    re.IGNORECASE,
)
_SIZE_GLUED = re.compile(
    rf"(\d+(?:\.\d+)?)(m|kg|g|ml|l|ltr)\b",
    re.IGNORECASE,
)

# Leading quantity + optional unit before product name within one clause.
_QTY_PREFIX = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)?)\s*)?"
    r"(?:(kg|kgs|kilograms?|g|grams?|gm|gms|mg|ml|l|liters?|litres?|ltr|"
    r"packets?|packs?|bottles?|pcs?|pieces?|units?|nos\.?)\s+)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CartItemRequest:
    """One product line the customer wants to add."""

    item: str
    quantity: str
    search_phrase: str


@dataclass
class PendingQuantityBatch:
    """Awaiting how much the customer wants for one SKU before continuing a bulk add."""

    sku: str
    product_name: str
    item_label: str
    remaining: list[CartItemRequest]
    added_so_far: list[tuple[str, float, str]]


_AVAILABILITY_PHRASES = (
    "do you have",
    "do u have",
    "have you got",
    "in stock",
    "available",
    "how much",
    "what is the price",
    "price of",
    "cost of",
)


def looks_like_availability_question(text: str) -> bool:
    """Product browse / stock check — not a direct purchase line."""
    lower = (text or "").lower()
    return any(p in lower for p in _AVAILABILITY_PHRASES)


def catalog_pack_size_token(product_name: str, sku: str = "") -> str | None:
    """Size baked into catalogue line, e.g. ``30m`` on cling wrap."""
    for source in (product_name or "", sku or ""):
        m = _SIZE_IN_TEXT.search(source)
        if not m:
            m = _SIZE_GLUED.search(source)
        if m:
            unit = m.group(2).lower().rstrip(".")
            val = m.group(1)
            if unit in ("m", "metre", "meter", "metres", "meters"):
                return f"{val}m"
            return f"{val} {unit}"
    return None


def reply_matches_catalog_pack_size(text: str, product_name: str, sku: str = "") -> bool:
    """User answered with the pack size shown in the product name (e.g. ``30m``)."""
    token = catalog_pack_size_token(product_name, sku)
    if not token:
        return False
    raw = (text or "").strip().lower()
    compact = re.sub(r"\s+", "", raw)
    token_compact = re.sub(r"\s+", "", token.lower())
    if compact == token_compact:
        return True
    if compact in token_compact or token_compact in compact:
        return len(compact) >= 2
    return False


def implies_single_catalog_pack(product_name: str, sku: str, item_label: str) -> bool:
    """One catalogue pack size; customer named the product only (e.g. cling wrap → Cling wrap 30m)."""
    label = (item_label or "").strip()
    if not label or customer_quantity_specified(clause_to_cart_request(label)):
        return False
    if not catalog_pack_size_token(product_name, sku):
        return False
    name_l = product_name.lower()
    words = [w for w in re.findall(r"[a-z]{3,}", label.lower())]
    return bool(words) and all(w in name_l for w in words)


def _variant_size_tokens(quantity: str) -> list[str]:
    """Compact size keys for matching catalogue packs, e.g. ``5kg`` from ``5 kg``."""
    q = (quantity or "").strip().lower()
    if not q:
        return []
    if re.fullmatch(r"\d+(?:\.\d+)?", q):
        return [q]

    m = _SIZE_IN_TEXT.search(q)
    if not m:
        m = _SIZE_GLUED.search(q)
    if not m:
        return []

    val = m.group(1)
    unit = m.group(2).lower().rstrip(".")
    unit = {
        "kgs": "kg",
        "kilograms": "kg",
        "kilogram": "kg",
        "grams": "g",
        "gram": "g",
        "gm": "g",
        "gms": "g",
        "liters": "l",
        "litres": "l",
        "liter": "l",
        "litre": "l",
        "ltr": "l",
    }.get(unit, unit)
    compact = f"{val}{unit}"
    spaced = f"{val} {unit}"
    return [compact, spaced] if compact != spaced else [compact]


def quantity_selects_product_variant(quantity: str, product_name: str, sku: str) -> bool:
    """Quantity names the catalogue pack (eggs ``12``, atta ``5 kg`` → 5kg SKU)."""
    q = (quantity or "").strip()
    if not q:
        return False

    name_l = (product_name or "").lower()
    name_compact = re.sub(r"\s+", "", name_l)
    sku_u = (sku or "").upper()
    sku_compact = re.sub(r"[^A-Z0-9]", "", sku_u)

    tokens = _variant_size_tokens(q)
    if not tokens:
        return False

    for tok in tokens:
        tok_compact = re.sub(r"\s+", "", tok.lower())
        if tok_compact and tok_compact in name_compact:
            return True

        if not re.fullmatch(r"\d+(?:\.\d+)?", tok):
            num_m = re.match(r"^(\d+(?:\.\d+)?)", tok_compact)
            if not num_m:
                continue
            num = num_m.group(1)
            unit = tok_compact[len(num) :]
            if unit and (
                sku_u.endswith(f"-{num}{unit.upper()}")
                or sku_compact.endswith(f"{num}{unit.upper()}")
            ):
                return True
            continue

        q_int = tok.split(".", 1)[0]
        if (
            sku_u.endswith(f"-{q_int}")
            or f"-{q_int}" in sku_u
            or f"({q_int} " in name_l
            or f"({tok} " in name_l
            or f"{q_int} pieces" in name_l
            or f"{q_int} piece" in name_l
        ):
            return True
    return False


def intent_quantity_is_variant_only(req: CartItemRequest, product_name: str, sku: str) -> bool:
    """Intent ``quantity`` field selects SKU size, not how many packs to order."""
    q = (req.quantity or "").strip()
    if not q:
        return False
    return quantity_selects_product_variant(q, product_name, sku)


def customer_quantity_specified(req: CartItemRequest) -> bool:
    """True when the customer gave an order quantity (not just a product name)."""
    if (req.quantity or "").strip():
        return True
    return bool(clause_to_cart_request(req.search_phrase or req.item).quantity)


def pair_items_and_quantities(items: list[str], quantities: list[str]) -> list[CartItemRequest]:
    """Align parallel ``items`` / ``quantities`` arrays from intent JSON."""
    cleaned_items = [str(x).strip() for x in items if str(x).strip()]
    if not cleaned_items:
        return []

    out: list[CartItemRequest] = []
    for i, item in enumerate(cleaned_items):
        q = ""
        if i < len(quantities):
            q = str(quantities[i]).strip()
        phrase = f"{q} {item}".strip() if q else item
        out.append(CartItemRequest(item=item, quantity=q, search_phrase=phrase))
    return out


def split_comma_separated_cart_message(text: str) -> list[str]:
    """Split a multi-item order string into per-product clauses."""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(raw) if p.strip()]
    if len(parts) >= 2:
        return parts
    # Fallback: comma without following space ("a, b" still splits)
    if "," in raw:
        loose = [p.strip() for p in raw.split(",") if p.strip()]
        if len(loose) >= 2:
            return loose
    return [raw] if raw else []


def clause_to_cart_request(clause: str) -> CartItemRequest:
    """Best-effort item + quantity from one clause like ``toor dal 4 kg``."""
    c = (clause or "").strip()
    if not c:
        return CartItemRequest(item="", quantity="", search_phrase="")

    m = _SIZE_IN_TEXT.search(c)
    if m:
        qty = f"{m.group(1)} {m.group(2)}"
        item = (c[: m.start()] + c[m.end() :]).strip(" ,;-")
        item = re.sub(r"^\s*(?:of|x)\s+", "", item, flags=re.IGNORECASE)
        return CartItemRequest(
            item=item or c,
            quantity=qty,
            search_phrase=c,
        )

    m_glue = _SIZE_GLUED.search(c)
    if m_glue:
        qty = f"{m_glue.group(1)}{m_glue.group(2)}"
        item = (c[: m_glue.start()] + c[m_glue.end() :]).strip(" ,;-")
        return CartItemRequest(
            item=item or c,
            quantity=qty,
            search_phrase=c,
        )

    m2 = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:x|×)?\s*$|\b(\d+)\s*(?:packets?|packs?|bottles?|pcs?|pieces?)\b",
        c,
        re.IGNORECASE,
    )
    if m2:
        num = m2.group(1) or m2.group(2)
        qty = num or ""
        item = c[: m2.start()].strip(" ,;-") if m2.start() else c
        phrase = f"{qty} {item}".strip() if qty and item else c
        return CartItemRequest(item=item or c, quantity=qty, search_phrase=phrase)

    return CartItemRequest(item=c, quantity="", search_phrase=c)


def build_cart_requests_from_entities(
    entities: IntentEntities | None,
    *,
    raw_text: str = "",
    normalized_query: str = "",
) -> list[CartItemRequest]:
    """Build cart line requests from classifier entities and/or comma-separated text."""
    ent = entities or IntentEntities()
    items = list(ent.items or [])
    quantities = list(ent.quantities or [])

    if len(items) >= 2:
        return pair_items_and_quantities(items, quantities)

    blob = (normalized_query or raw_text or "").strip()
    clauses = split_comma_separated_cart_message(blob)
    if len(clauses) >= 2:
        return [clause_to_cart_request(c) for c in clauses]

    if len(items) == 1:
        return pair_items_and_quantities(items, quantities)

    return []


def is_multi_item_add_request(
    entities: IntentEntities | None,
    *,
    raw_text: str = "",
    normalized_query: str = "",
) -> bool:
    return len(build_cart_requests_from_entities(entities, raw_text=raw_text, normalized_query=normalized_query)) >= 2
