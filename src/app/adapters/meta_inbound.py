"""Parse Meta WhatsApp Cloud API webhook payloads into orchestrator payloads."""

from __future__ import annotations

import re
from typing import Any, Iterator

from app.services.menu_commands import is_menu_command

# SKU pattern: letters/digits with at least one hyphen segment (e.g. RICE-1KG).
_SKU_RE = re.compile(r"\b([A-Z0-9]{2,}(?:-[A-Z0-9]+)+)\b")

# Natural-language hints for catalogue / stock lookup (no structured SKU).
_CATALOG_SEARCH_HINTS = (
    "in stock",
    "in-stock",
    "do you have",
    "have you got",
    "do you carry",
    "available",
    "availability",
    "got any",
    "any stock",
    "still have",
    "carry ",
    "price of",
    "price for",
    "how much is",
    "how much for",
    "cost of",
    "cost for",
)


def iter_meta_message_bundles(body: dict[str, Any]) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Yield (value, message) for each inbound WhatsApp message."""
    if body.get("object") != "whatsapp_business_account":
        return
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                yield value, msg


def iter_meta_messages(body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield raw message objects (backwards compatible)."""
    for _value, msg in iter_meta_message_bundles(body):
        yield msg


def message_to_orchestrator_payload(
    from_wa_id: str,
    msg: dict[str, Any],
    store_id: str,
) -> dict[str, Any]:
    """Map one WhatsApp message to our orchestrator payload (includes ``store_id``)."""
    mtype = msg.get("type")
    phone = from_wa_id if from_wa_id.startswith("+") else f"+{from_wa_id}"

    if mtype == "text":
        text = (msg.get("text") or {}).get("body") or ""
        payload = _text_to_payload(phone, text.strip())
        payload["store_id"] = store_id
        return payload

    if mtype == "audio":
        audio_id = (msg.get("audio") or {}).get("id") or ""
        return {
            "intent": "audio",
            "phone": phone,
            "store_id": store_id,
            "audio_url": f"whatsapp-media:{audio_id}" if audio_id else "",
        }

    return {
        "intent": "question",
        "phone": phone,
        "store_id": store_id,
        "message": f"(Unsupported message type: {mtype})",
    }


def _wants_catalog_search(lower: str, skus: list[str]) -> bool:
    if skus:
        return False
    return any(h in lower for h in _CATALOG_SEARCH_HINTS)


def _text_to_payload(phone: str, text: str) -> dict[str, Any]:
    lower = text.lower()
    skus = _SKU_RE.findall(text.upper())

    if lower.strip() in {"hi", "hello", "hey"}:
        return {"intent": "greeting", "phone": phone, "customer_text": text}

    if is_menu_command(text):
        return {"intent": "menu", "phone": phone, "customer_text": text}

    # Structured availability: "stock RICE-1KG", "available TEA-500G"
    if skus and any(k in lower for k in ("stock", "available", "availability")):
        return {"intent": "availability", "phone": phone, "sku": skus[0], "customer_text": text}

    # Free-text stock / price questions → search this store's catalogue file
    if _wants_catalog_search(lower, skus):
        return {"intent": "availability_search", "phone": phone, "query": text, "customer_text": text}

    pay_match = re.match(r"^pay\s+([a-f0-9-]{36})\s*$", lower.strip())
    if pay_match:
        return {"intent": "pay", "phone": phone, "order_id": pay_match.group(1), "customer_text": text}

    cancel_match = re.match(r"^cancel\s+([a-f0-9-]{36})\s*$", lower.strip())
    if cancel_match:
        return {"intent": "cancel_order", "phone": phone, "order_id": cancel_match.group(1), "customer_text": text}

    order_match = re.match(
        r"^order\s+([A-Z0-9]{2,}(?:-[A-Z0-9]+)+)\s+(\d+)\s*$",
        text.strip(),
        flags=re.IGNORECASE,
    )
    if order_match:
        sku, qty = order_match.group(1).upper(), int(order_match.group(2))
        return {
            "intent": "place_order",
            "phone": phone,
            "items": [{"sku": sku, "quantity": qty}],
            "customer_text": text,
        }

    payload: dict[str, Any] = {"intent": "question", "phone": phone, "message": text, "customer_text": text}
    if skus:
        payload["sku"] = skus[0]
    return payload
