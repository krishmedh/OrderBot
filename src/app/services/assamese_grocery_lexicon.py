"""Romanized Assamese grocery phrases → canonical product keys for intent/cart."""

from __future__ import annotations

import re

from app.domain.intent_classification import IntentClassification, ItemIntent

# Tea leaves: saah/saa/cha + paat (চাহ পাত)
_TEA_LEAVES_RE = re.compile(
    r"\b(?:saa?h?|saah|cha)\s*paat\b",
    re.IGNORECASE,
)
# Tea (beverage) without "paat": "saa laage", "tea laage"
_TEA_SHORT_RE = re.compile(
    r"\b(?:saa?h?|saah)\s+(?:u\s+)?la+a?g",
    re.IGNORECASE,
)
_TEA_EN_RE = re.compile(r"\btea\b", re.IGNORECASE)
_SOAP_RE = re.compile(r"\bsabun\b|\bxabun\b", re.IGNORECASE)
_WANT_RE = re.compile(
    r"\bla+a?g[ei]\b|\blagise\b|\blagibo\b|\blage\b",
    re.IGNORECASE,
)
_SOAP_LLM_KEYS = frozenset({"soap", "sabun", "lux", "bathing soap"})
# Product-in-stock questions: "<alias> ase neki" (Assamese)
_AVAILABILITY_QUESTION_RE = re.compile(
    r"\base(?:\s+neki|\s+niki|\s+ne\b|\?)\b",
    re.IGNORECASE,
)
# Open catalogue only when no product alias is present
_OPEN_CATALOGUE_RE = re.compile(
    r"\bki\s+(?:\w+\s+)?ase(?:\s+neki)?\b"
    r"|\b(?:ache|ase)\s+ki\b"
    r"|\bki\s+ki\s+ase\b",
    re.IGNORECASE,
)
# Romanized product aliases → normalized catalogue key (order: longer phrases first)
_PRODUCT_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:saa?h?\s*paat|cha\s*paat)\b", re.I), "tea leaves"),
    (re.compile(r"\b(?:koni|dim)\b", re.I), "eggs"),
    (re.compile(r"\b(?:dali|daali)\b", re.I), "dal"),
    (re.compile(r"\bsabun\b", re.I), "soap"),
    (re.compile(r"\b(?:chaul|saul)\b", re.I), "rice"),
    (re.compile(r"\bdudh\b", re.I), "milk"),
    (re.compile(r"\btel\b", re.I), "cooking oil"),
]


_PACK_HINT_RE = re.compile(
    r"\b(\d+)\s*(?:pack|packs|pkt|packets?|piece|pieces|pcs)\b",
    re.IGNORECASE,
)
_EN_AVAILABILITY_RE = re.compile(
    r"\b(?:is|are)\s+.+\s+available\b|\bavailable\??\b",
    re.IGNORECASE,
)


def _availability_pack_hint(text: str) -> str:
    m = _PACK_HINT_RE.search(text or "")
    if not m:
        return ""
    return f"{m.group(1)} pack"


def detect_product_availability_query(text: str) -> str | None:
    """e.g. ``koni ase neki`` or ``12 pack koni ase neki`` → eggs."""
    t = (text or "").strip()
    if not t:
        return None
    has_avail = bool(
        _AVAILABILITY_QUESTION_RE.search(t) or _EN_AVAILABILITY_RE.search(t)
    )
    if not has_avail:
        return None
    for pat, key in _PRODUCT_ALIASES:
        if pat.search(t):
            return key
    if re.search(r"\beggs?\b", t, re.IGNORECASE):
        return "eggs"
    return None


def is_open_catalogue_question(text: str) -> bool:
    """What's in stock / what do you sell — no specific product named."""
    t = (text or "").strip()
    if not t or _WANT_RE.search(t) or detect_product_availability_query(t):
        return False
    if detect_assamese_products(t):
        return False
    return bool(_OPEN_CATALOGUE_RE.search(t))


def mentions_tea_leaves(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _TEA_LEAVES_RE.search(t):
        return True
    if _TEA_EN_RE.search(t) and _WANT_RE.search(t):
        return True
    if _TEA_SHORT_RE.search(t) and not _SOAP_RE.search(t):
        return True
    return False


def mentions_soap(text: str) -> bool:
    return bool(_SOAP_RE.search(text or ""))


def detect_assamese_products(text: str) -> list[tuple[str, str]]:
    """Return (item_key, english_label) pairs mentioned in the message."""
    found: list[tuple[str, str]] = []
    if mentions_tea_leaves(text):
        found.append(("tea leaves", "tea leaves"))
    if mentions_soap(text):
        found.append(("soap", "bathing soap"))
    return found


def _looks_like_fresh_add_request(text: str) -> bool:
    return bool(_WANT_RE.search(text or ""))


def apply_assamese_lexicon(
    classification: IntentClassification,
    user_text: str,
) -> IntentClassification:
    """
    Correct common LLM mistakes on Assamese grocery chat.

    Example: ``saa paat u laage`` (need tea leaves) must not become Lux soap.
    """
    text = (user_text or "").strip()
    avail_product = detect_product_availability_query(text)
    if avail_product:
        pack = _availability_pack_hint(text)
        label = f"{pack} {avail_product}".strip() if pack else avail_product
        return classification.model_copy(
            update={
                "items": {
                    avail_product: ItemIntent(
                        intent="grocery",
                        sub_intent="query_items",
                        quantity=pack,
                        normalized_query=f"Check if {label} are available",
                    )
                },
                "language": "as",
            }
        )

    if is_open_catalogue_question(text):
        return classification.model_copy(
            update={
                "items": {
                    "catalogue": ItemIntent(
                        intent="grocery",
                        sub_intent="query_items",
                        quantity="",
                        normalized_query="What products are available in the store?",
                    )
                },
                "language": "as",
            }
        )

    products = detect_assamese_products(text)
    if not products:
        return classification

    items = dict(classification.items)
    fresh_add = _looks_like_fresh_add_request(text)

    if mentions_tea_leaves(text) and not mentions_soap(text):
        for key in list(items):
            if key.lower() in _SOAP_LLM_KEYS:
                items.pop(key, None)

    for key, label in products:
        if key in items:
            item = items[key]
            if fresh_add and item.sub_intent == "modify_item_from_cart":
                items[key] = item.model_copy(
                    update={
                        "sub_intent": "add_to_cart",
                        "quantity": "",
                        "normalized_query": f"Add {label} to cart",
                    }
                )
            continue
        items[key] = ItemIntent(
            intent="grocery",
            sub_intent="add_to_cart",
            quantity="",
            normalized_query=f"Add {label} to cart",
        )

    lang = classification.language
    if lang in ("en", "") and products:
        lang = "mixed"

    return classification.model_copy(update={"items": items, "language": lang})
