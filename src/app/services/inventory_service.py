from __future__ import annotations

import re

from app.domain.models import Product
from app.services.catalog_fuzzy import fuzzy_rank_products, product_search_tokens
from app.services.store_inventory_locator import StoreInventoryLocator

# Same idea as Meta inbound: structured SKUs in free text.
_SKU_IN_TEXT = re.compile(r"\b([A-Z0-9]{2,}(?:-[A-Z0-9]+)+)\b", re.IGNORECASE)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "and",
        "or",
        "but",
        "if",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "we",
        "you",
        "i",
        "me",
        "my",
        "your",
        "our",
        "their",
        "them",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "how",
        "when",
        "where",
        "why",
        "any",
        "some",
        "all",
        "each",
        "every",
        "no",
        "not",
        "only",
        "just",
        "also",
        "too",
        "very",
        "there",
        "here",
        "then",
        "than",
        "into",
        "from",
        "with",
        "about",
        "over",
        "under",
        "again",
        "once",
        "please",
        "thanks",
        "thank",
        "hello",
        "hi",
        "hey",
        "yes",
        "ok",
        "tell",
        "give",
        "know",
        "like",
        "want",
        "need",
        "get",
        "got",
        "still",
        "stock",
        "available",
        "availability",
        "price",
        "cost",
        "carry",
        "sell",
        "selling",
        "buy",
        "buying",
        "much",
        "question",
        "questions",
        "information",
        "info",
        "help",
        "something",
        "anything",
        "things",
        "thing",
        "stuff",
        "items",
        "item",
        "household",
        "home",
        "necessities",
        "needs",
        "essentials",
        "basics",
        "provision",
        "provisions",
        "supplies",
        "groceries",
        "sundries",
        "pantry",
        "consumables",
        "else",
        "latest",
        "check",
        "checking",
        "website",
        "store",
        "sorry",
        "dont",
        "doesnt",
        "im",
    }
)


_SIZE_TOKEN = re.compile(
    r"^(?:\d+(?:\.\d+)?)(?:kg|kgs|g|grams?|ml|l|liters?|litres?|ltr)$",
    re.IGNORECASE,
)

_SPELLING_ALIASES: dict[str, str] = {
    "choclate": "chocolate",
    "choc": "chocolate",
    "chocolate": "chocolate",
    "mustart": "mustard",
    "musturd": "mustard",
    "refine": "refined",
    "sunflowr": "sunflower",
}


def _normalize_token(token: str) -> str:
    t = token.lower()
    return _SPELLING_ALIASES.get(t, t)


def _is_size_token(token: str) -> bool:
    return bool(_SIZE_TOKEN.match(token.strip()))


_GENERAL_QUESTION_WORDS = frozenset(
    {
        "delivery",
        "deliver",
        "hours",
        "hour",
        "open",
        "close",
        "closed",
        "timing",
        "time",
        "when",
        "where",
        "how",
        "why",
        "help",
        "support",
        "contact",
        "address",
        "location",
        "sunday",
        "monday",
        "today",
        "tomorrow",
    }
)


def extract_product_keywords(query: str) -> list[str]:
    """Non-size tokens that look like a product name (not general FAQ words)."""
    raw = [_normalize_token(t) for t in _meaningful_tokens(query)]
    return [t for t in raw if not _is_size_token(t) and t not in _GENERAL_QUESTION_WORDS]


def _raw_tokens(query: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", query.lower())


def _extract_skus(query: str) -> list[str]:
    return [m.group(1).upper() for m in _SKU_IN_TEXT.finditer(query)]


def _meaningful_tokens(query: str) -> list[str]:
    raw = _raw_tokens(query)
    filtered = [t for t in raw if t not in _STOPWORDS and len(t) >= 2]
    if filtered:
        return filtered
    return [t for t in raw if len(t) >= 3]


def _sku_segments(sku: str) -> set[str]:
    return {s.lower() for s in sku.split("-") if s}


def _token_covers_sku_hyphen_token(token: str, segments: set[str]) -> bool:
    if "-" not in token:
        return False
    parts = [p for p in token.split("-") if p]
    return bool(parts) and set(parts) <= segments


def _word_boundary(token: str, hay: str) -> bool:
    if len(token) < 2:
        return False
    return re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", hay, re.IGNORECASE) is not None


def _product_matches_query(product: Product, skus: list[str], tokens: list[str]) -> bool:
    sku_upper = product.sku.upper()
    for s in skus:
        if s == sku_upper:
            return True

    name_l = product.name.lower()
    sku_l = product.sku.lower()
    segments = _sku_segments(product.sku)

    for t in tokens:
        if t in segments or _token_covers_sku_hyphen_token(t, segments):
            return True
        if _word_boundary(t, name_l) or _word_boundary(t, sku_l):
            return True
    return False


class InventoryService:
    def __init__(self, locator: StoreInventoryLocator) -> None:
        self._locator = locator

    def get_product(self, store_id: str | None, sku: str) -> Product | None:
        return self._locator.get(store_id).get_product(sku)

    def check_availability(self, store_id: str | None, sku: str) -> str:
        repo = self._locator.get(store_id)
        product = repo.get_product(sku)
        if not product:
            return f"Product with SKU {sku} is not found."
        return (
            f"{product.name} ({product.sku}) is available: "
            f"{product.quantity_available} units, price {product.price:.2f}"
        )

    def list_all_products(self, store_id: str | None) -> list[Product]:
        return self._locator.get(store_id).list_products()

    def catalog_matches(self, store_id: str | None, query: str) -> list[Product]:
        """Match products by SKU, token overlap, and fuzzy name similarity."""
        q = (query or "").strip()
        if not q:
            return []
        repo = self._locator.get(store_id)
        products = repo.list_products()
        known_skus = {p.sku.upper() for p in products}
        # Hyphenated product names (e.g. parle-g) must not be treated as catalogue SKUs.
        skus = [s for s in _extract_skus(q) if s in known_skus]
        raw = [_normalize_token(t) for t in _meaningful_tokens(q)]
        product_tokens = extract_product_keywords(q)
        search_tokens = product_search_tokens(q, product_tokens)
        size_tokens = [t for t in raw if _is_size_token(t)]

        if not skus and not search_tokens:
            return []
        # Size-only query (e.g. "200g") must not fuzzy-match every product with that size.
        if size_tokens and not search_tokens:
            return []

        if skus:
            exact = [p for p in products if p.sku.upper() in skus]
            if exact:
                if size_tokens:
                    exact = [
                        p
                        for p in exact
                        if any(
                            st in p.name.lower() or st in p.sku.lower() for st in size_tokens
                        )
                    ]
                return exact

        ranked = fuzzy_rank_products(
            products,
            q,
            product_tokens=search_tokens,
            exact_skus=skus or None,
        )
        if size_tokens:
            ranked = [
                p
                for p in ranked
                if any(st in p.name.lower() or st in p.sku.lower() for st in size_tokens)
            ]
        return ranked

    def format_catalog_matches(self, matches: list[Product]) -> str:
        lines = [
            f"- {p.name} ({p.sku}): {p.quantity_available} in stock, price {p.price:.2f}"
            for p in matches[:15]
        ]
        extra = "" if len(matches) <= 15 else f"\n… and {len(matches) - 15} more matches."
        return "Here is what we found:\n" + "\n".join(lines) + extra

    def search_catalog(self, store_id: str | None, query: str) -> str:
        """Match products using words and SKUs inside the customer's question."""
        q = (query or "").strip()
        if not q:
            return "Please name the product or SKU you want to check."
        matches = self.catalog_matches(store_id, q)
        if not matches:
            return (
                f"No items in this store's catalogue matched \"{q}\". "
                "Try a product name, part of the name, or a SKU (for example RICE-1KG)."
            )
        return self.format_catalog_matches(matches)
