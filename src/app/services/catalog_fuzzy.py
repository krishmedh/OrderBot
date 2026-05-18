"""Fuzzy scoring for catalogue product lookup (typos, spacing, phonetic spellings)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.domain.models import Product

# Tokens that are not part of a product name (quantity / cart phrasing).
_SIZE_TOKEN = re.compile(
    r"^(?:\d+(?:\.\d+)?)(?:kg|kgs|g|grams?|ml|l|liters?|litres?|ltr)$",
    re.IGNORECASE,
)

_UNIT_ONLY = frozenset(
    {"kg", "kgs", "g", "gm", "gram", "grams", "ml", "l", "ltr", "litre", "liter", "litres", "liters"}
)

_NON_PRODUCT_TOKENS = frozenset(
    {
        "pkt",
        "pkts",
        "pack",
        "packs",
        "packet",
        "packets",
        "pc",
        "pcs",
        "piece",
        "pieces",
        "more",
        "aaru",
        "laage",
        "lage",
        "lagibo",
        "chahiye",
        "diya",
        "dibo",
        "de",
        "add",
        "need",
        "want",
        "order",
        "buy",
    }
)

_MIN_TOKEN_LEN_FUZZY = 4
_FUZZY_TOKEN_RATIO = 0.82
_FUZZY_NAME_RATIO = 0.58
_FUZZY_MIN_SCORE = 50.0
_FUZZY_AMBIGUITY_GAP = 12.0
_MAX_FUZZY_RESULTS = 12


def normalize_match_text(text: str) -> str:
    """Lowercase phrase with hyphens/punctuation collapsed for comparison."""
    t = (text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _name_tokens(name: str) -> list[str]:
    return [w for w in normalize_match_text(name).split() if len(w) >= 2]


def _fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _token_fuzzy_match(query_token: str, hay: str, name_tokens: list[str]) -> float:
    if len(query_token) < 2:
        return 0.0
    if _word_boundary_exact(query_token, hay):
        return 1.0
    if len(query_token) < _MIN_TOKEN_LEN_FUZZY:
        return 0.0
    best = 0.0
    for nt in name_tokens:
        if len(nt) < _MIN_TOKEN_LEN_FUZZY:
            continue
        best = max(best, _fuzzy_ratio(query_token, nt))
        if query_token in nt or nt in query_token:
            best = max(best, 0.9)
    return best


def _word_boundary_exact(token: str, hay: str) -> bool:
    if len(token) < 2:
        return False
    return re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", hay, re.IGNORECASE) is not None


def _sku_segment_match(query: str, product: Product) -> float:
    segments = {s.lower() for s in product.sku.split("-") if len(s) >= 2}
    best = 0.0
    for token in normalize_match_text(query).split():
        if token in segments:
            best = max(best, 1.0)
        elif "-" in token:
            parts = [p for p in token.split("-") if p]
            if parts and set(parts) <= segments:
                best = max(best, 0.95)
        for seg in segments:
            if len(token) >= _MIN_TOKEN_LEN_FUZZY and len(seg) >= _MIN_TOKEN_LEN_FUZZY:
                best = max(best, _fuzzy_ratio(token, seg))
    return best


def _is_size_or_unit_token(token: str) -> bool:
    t = (token or "").strip().lower()
    if not t:
        return True
    if t in _UNIT_ONLY:
        return True
    return bool(_SIZE_TOKEN.match(t))


def product_search_tokens(query: str, product_tokens: list[str]) -> list[str]:
    """Product-name tokens used for scoring (drops pack/qty/size noise)."""
    out: list[str] = []
    for t in product_tokens:
        if t in _NON_PRODUCT_TOKENS or _is_size_or_unit_token(t):
            continue
        if len(t) >= 2:
            out.append(t)
    if out:
        return out
    raw = [
        w
        for w in normalize_match_text(query).split()
        if w not in _NON_PRODUCT_TOKENS and not _is_size_or_unit_token(w)
    ]
    return [w for w in raw if len(w) >= 2]


def score_product_match(
    product: Product,
    query: str,
    *,
    product_tokens: list[str] | None = None,
    exact_skus: list[str] | None = None,
) -> float:
    """
    Score how well ``query`` matches a catalogue product (0–100).
    Higher is better; ``FUZZY_MIN_SCORE`` is the usual cutoff.
    """
    q = (query or "").strip()
    if not q:
        return 0.0

    sku_upper = product.sku.upper()
    if exact_skus and sku_upper in exact_skus:
        return 100.0

    tokens = product_search_tokens(q, list(product_tokens or []))
    name_l = product.name.lower()
    sku_l = product.sku.lower()
    name_norm = normalize_match_text(product.name)
    query_norm = normalize_match_text(" ".join(tokens) if tokens else q)
    name_toks = _name_tokens(product.name)

    if not tokens:
        return 0.0

    token_scores: list[float] = []
    for t in tokens:
        ts = _token_fuzzy_match(t, name_l, name_toks)
        ts = max(ts, _token_fuzzy_match(t, sku_l, []))
        token_scores.append(ts)

    if not token_scores:
        return 0.0

    # Every product keyword should match reasonably (weakest link with floor).
    min_tok = min(token_scores)
    avg_tok = sum(token_scores) / len(token_scores)
    if min_tok < 0.55 and avg_tok < 0.72:
        return 0.0

    name_ratio = _fuzzy_ratio(query_norm, name_norm)
    sku_seg = _sku_segment_match(q, product)

    score = (
        min_tok * 38.0
        + avg_tok * 28.0
        + name_ratio * 22.0
        + sku_seg * 12.0
    )
    if min_tok >= 0.98:
        score = max(score, 78.0)
    if name_ratio >= 0.88:
        score = max(score, 85.0)
    return min(100.0, score)


def fuzzy_rank_products(
    products: list[Product],
    query: str,
    *,
    product_tokens: list[str] | None = None,
    exact_skus: list[str] | None = None,
    min_score: float = _FUZZY_MIN_SCORE,
    max_results: int = _MAX_FUZZY_RESULTS,
) -> list[Product]:
    """Return products ranked by fuzzy score (best first)."""
    scored: list[tuple[float, Product]] = []
    for p in products:
        s = score_product_match(
            p, query, product_tokens=product_tokens, exact_skus=exact_skus
        )
        if s >= min_score:
            scored.append((s, p))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], x[1].name))
    top = scored[0][0]
    cutoff = max(min_score, top - _FUZZY_AMBIGUITY_GAP)
    return [p for s, p in scored if s >= cutoff][:max_results]
