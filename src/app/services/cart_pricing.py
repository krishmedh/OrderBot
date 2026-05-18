"""Cart line pricing from catalogue pack size and requested weight."""

from __future__ import annotations

import math
import re

from app.domain.models import Product
from app.services.shopping_session import parse_quantity_from_text

_WEIGHT_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|kgs|kilograms?|g|grams?|gm|gms|mg|ml|l|liters?|litres?|ltr)\b",
    re.IGNORECASE,
)

_PACK_SIZE_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|kgs|kilograms?|g|grams?|gm|gms|mg|ml|l|liters?|litres?|ltr)\b",
    re.IGNORECASE,
)

_LENGTH_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(m|metres?|meters?)\b",
    re.IGNORECASE,
)
_LENGTH_GLUED = re.compile(r"(\d+(?:\.\d+)?)(m)\b", re.IGNORECASE)


def _to_grams(value: float, unit: str) -> float:
    u = unit.lower().rstrip(".")
    if u in ("kg", "kgs", "kilogram", "kilograms"):
        return value * 1000.0
    if u in ("g", "gram", "grams", "gm", "gms"):
        return value
    if u in ("mg",):
        return value / 1000.0
    if u in ("l", "liter", "litre", "liters", "litres", "ltr"):
        return value * 1000.0  # treat as ml equivalent for dry goods priced per L
    if u in ("ml",):
        return value
    return value


def parse_weight_grams(text: str) -> float | None:
    """First weight measure in text, normalised to grams."""
    m = _WEIGHT_TOKEN.search(text or "")
    if not m:
        return None
    return _to_grams(float(m.group(1)), m.group(2))


def parse_pack_size_grams(name: str, sku: str) -> float | None:
    """Pack size from product name or SKU (e.g. Moong dal 1kg, DAL-MOONG-1KG)."""
    for source in (name or "", sku or ""):
        m = _PACK_SIZE_TOKEN.search(source)
        if m:
            return _to_grams(float(m.group(1)), m.group(2))
    return None


def parse_length_meters(text: str) -> float | None:
    """First length in metres from customer text (e.g. ``60m``, ``60 m``)."""
    raw = text or ""
    m = _LENGTH_TOKEN.search(raw)
    if m:
        return float(m.group(1))
    m = _LENGTH_GLUED.search(raw)
    if m:
        return float(m.group(1))
    return None


def parse_pack_length_meters(name: str, sku: str) -> float | None:
    """Roll length from product name (e.g. Cling wrap 30m)."""
    for source in (name or "", sku or ""):
        m = _LENGTH_TOKEN.search(source)
        if m:
            return float(m.group(1))
        m = _LENGTH_GLUED.search(source)
        if m:
            return float(m.group(1))
    return None


def format_meters_label(meters: float) -> str:
    if meters == int(meters):
        return f"{int(meters)} m"
    return f"{meters:.1f} m"


def format_weight_label(grams: float) -> str:
    if grams >= 1000 and grams % 1000 == 0:
        return f"{int(grams / 1000)} kg"
    if grams >= 1000:
        return f"{grams / 1000:.2f} kg"
    return f"{int(grams)} g"


def compute_cart_line(
    product: Product,
    user_text: str,
    *,
    pack_count_override: int | None = None,
) -> tuple[int, float, str]:
    """
    Return (packs_to_deduct_from_stock, line_total_inr, note_for_customer).

    Example: Moong dal 1kg @ 105 INR, customer asks for 5 kg → 5 packs, 525 INR.
    Customer asks for 250 g → 1 pack, 26.25 INR.
    """
    pack_g = parse_pack_size_grams(product.name, product.sku)
    req_g = parse_weight_grams(user_text)
    pack_count = pack_count_override if pack_count_override is not None else parse_quantity_from_text(user_text, 1)

    if pack_g and req_g and pack_g > 0:
        # e.g. "2 mustard 1 litre" — leading pack count, size token is the SKU pack size
        if pack_count > 1 and abs(req_g - pack_g) < 0.01:
            packs = pack_count
            line_total = round(product.price * packs, 2)
            note = f"{packs} pack(s)"
            return packs, line_total, note

        mult = req_g / pack_g
        if mult <= 0:
            mult = 1.0
        if mult < 1:
            packs = 1
            line_total = round(product.price * mult, 2)
            note = f"{format_weight_label(req_g)} (priced from {format_weight_label(pack_g)} pack)"
        else:
            packs = max(1, int(round(mult))) if abs(mult - round(mult)) < 0.01 else math.ceil(mult)
            line_total = round(product.price * mult, 2)
            if packs == int(round(mult)) and abs(mult - int(round(mult))) < 0.01:
                note = f"{format_weight_label(req_g)} ({packs} × {format_weight_label(pack_g)} pack)"
            else:
                note = f"{format_weight_label(req_g)} ({packs} packs of {format_weight_label(pack_g)})"
        return packs, line_total, note

    pack_m = parse_pack_length_meters(product.name, product.sku)
    req_m = parse_length_meters(user_text)
    if pack_m and req_m and pack_m > 0:
        mult = req_m / pack_m
        if mult <= 0:
            mult = 1.0
        if mult < 1:
            packs = 1
            line_total = round(product.price * mult, 2)
            note = (
                f"{format_meters_label(req_m)} "
                f"(priced from {format_meters_label(pack_m)} roll)"
            )
        else:
            packs = (
                max(1, int(round(mult)))
                if abs(mult - round(mult)) < 0.01
                else math.ceil(mult)
            )
            line_total = round(product.price * mult, 2)
            if packs > 1 or abs(mult - 1) > 0.01:
                note = (
                    f"{format_meters_label(req_m)} "
                    f"({packs} × {format_meters_label(pack_m)} roll)"
                )
            else:
                note = format_meters_label(req_m)
        return packs, line_total, note

    packs = max(1, pack_count)
    line_total = round(product.price * packs, 2)
    note = f"{packs} pack(s)" if packs > 1 else ""
    return packs, line_total, note
