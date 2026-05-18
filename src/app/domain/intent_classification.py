"""Structured per-item intent output from the classification engine."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

GrocerySubIntent = Literal[
    "query_items",
    "add_to_cart",
    "remove_from_cart",
    "modify_item_from_cart",
    "delete_cart",
    "checkout",
    "general_enquiry",
    "view_cart",
]

LanguageCode = Literal["en", "hi", "as", "mixed"]
Urgency = Literal["LOW", "MEDIUM", "HIGH"]

# Normalized sub_intent aliases from older prompts / models
_SUB_INTENT_ALIASES: dict[str, str] = {
    "add_item_to_cart": "add_to_cart",
    "add_item": "add_to_cart",
    "remove_item_from_cart": "remove_from_cart",
    "remove_item": "remove_from_cart",
    "update_item": "modify_item_from_cart",
    "update_cart_item": "modify_item_from_cart",
    "modify_item": "modify_item_from_cart",
    "check_menu": "query_items",
    "compare_items": "query_items",
    "general_shopping_help": "general_enquiry",
    "view_cart": "view_cart",
    "delete_cart": "delete_cart",
    "checkout": "checkout",
    "query_items": "query_items",
    "general_enquiry": "general_enquiry",
}


def normalize_sub_intent(raw: str | None) -> str:
    key = (raw or "").strip().lower().replace("-", "_")
    if not key or key == "null":
        return "add_to_cart"
    return _SUB_INTENT_ALIASES.get(key, key)


class IntentEntities(BaseModel):
    """Parallel item/qty lists for bulk cart parsing (multi_item_cart)."""

    items: list[str] = Field(default_factory=list)
    quantities: list[str] = Field(default_factory=list)


class ItemIntent(BaseModel):
    intent: str = "grocery"
    sub_intent: str = "add_to_cart"
    quantity: str = ""
    normalized_query: str = ""

    @classmethod
    def from_raw(cls, data: object, *, item_key: str = "") -> ItemIntent | None:
        if not isinstance(data, dict):
            return None
        sub = normalize_sub_intent(str(data.get("sub_intent") or ""))
        intent = str(data.get("intent") or "grocery").strip().lower() or "grocery"
        qty = str(data.get("quantity") if data.get("quantity") is not None else "")
        nq = str(data.get("normalized_query") or "").strip()
        if not nq and item_key:
            nq = f"{sub.replace('_', ' ')} {item_key}".strip()
        return cls(
            intent=intent,
            sub_intent=sub,
            quantity=qty,
            normalized_query=nq,
        )


class IntentClassification(BaseModel):
    language: str = "en"
    urgency: str = "LOW"
    items: dict[str, ItemIntent] = Field(default_factory=dict)

    # Legacy fields used by logging / fallbacks (derived, not from model)
    confidence: float = 0.85
    context_used: str = "current"

    @property
    def intent(self) -> str:
        if not self.items:
            return "UNKNOWN"
        domains = {v.intent.lower() for v in self.items.values()}
        if domains == {"grocery"}:
            return "GROCERY_PURCHASE"
        return "GROCERY_PURCHASE" if "grocery" in domains else "UNKNOWN"

    @property
    def sub_intent(self) -> str | None:
        if len(self.items) == 1:
            return next(iter(self.items.values())).sub_intent
        return None

    @property
    def normalized_query(self) -> str:
        if not self.items:
            return ""
        parts = [v.normalized_query for v in self.items.values() if v.normalized_query]
        return "; ".join(parts)

    def grocery_items(self) -> list[tuple[str, ItemIntent]]:
        return [
            (key, val)
            for key, val in self.items.items()
            if (val.intent or "grocery").lower() in ("grocery", "grocery_purchase")
        ]

    def model_dump_json_safe(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "urgency": self.urgency,
            "items": {
                k: {
                    "intent": v.intent,
                    "sub_intent": v.sub_intent,
                    "quantity": v.quantity,
                    "normalized_query": v.normalized_query,
                }
                for k, v in self.items.items()
            },
            "confidence": self.confidence,
            "context_used": self.context_used,
        }
