"""Parse customer replies to a numbered product list (language-agnostic)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.shopping_session import parse_quantity_from_text

_DECLINE_RE = re.compile(
    r"(?i)^\s*(?:no|nope|nah|cancel|skip|stop|not\s+now|nahi\s+chahiye|nai\s+lag(?:e|ibo)?)\b"
)
# pack count then option index: "2 packet 1 number"
_PACK_THEN_OPTION_RE = re.compile(
    r"(?i)(?P<pack>\d{1,3})\s*pack(?:et)?s?\s*(?P<opt>\d{1,3})\s*(?:num(?:ber)?|no\.?)?\b"
)
_OPTION_THEN_PACK_RE = re.compile(
    r"(?i)(?P<opt>\d{1,3})\s*(?:num(?:ber)?|no\.?)\s*(?P<pack>\d{1,3})\s*pack(?:et)?s?\b"
)
_GLUE_INDEX_RE = re.compile(r"(?i)^\s*(\d{1,2})(?:tu|ta|t)\s*[,.\s!]*$")
_ORDINAL_RE = re.compile(
    r"(?i)\b("
    r"first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|"
    r"eighth|8th|ninth|9th|tenth|10th|"
    r"prothom|ditiyo|tritiyo|eta|duita|tinta"
    r")\b"
)
_ORDINAL_TO_INDEX: dict[str, int] = {
    "first": 0,
    "1st": 0,
    "prothom": 0,
    "eta": 0,
    "second": 1,
    "2nd": 1,
    "ditiyo": 1,
    "duita": 1,
    "third": 2,
    "3rd": 2,
    "tritiyo": 2,
    "tinta": 2,
    "fourth": 3,
    "4th": 3,
    "fifth": 4,
    "5th": 4,
    "sixth": 5,
    "6th": 5,
    "seventh": 6,
    "7th": 6,
    "eighth": 7,
    "8th": 7,
    "ninth": 8,
    "9th": 8,
    "tenth": 9,
    "10th": 9,
}
_OPTION_DIGIT_RES: list[re.Pattern[str]] = [
    re.compile(r"(?i)^\s*(\d{1,2})\s*[,.\s]*(?:please|pls|plz|tu|ta|diya|lage|lagibo|dibo|add|kori)?\s*$"),
    re.compile(r"(?i)\b(?:option|number|no\.?)\s*(\d{1,2})\b"),
    re.compile(r"(?i)\b(?:go\s+with|take|choose|send|add|pick|select)\s*(\d{1,2})\b"),
    re.compile(
        r"(?i)\b(?:give\s+me|i\s*want|i'?ll\s+take|i\s+need|get)\s*(?:option\s*)?(\d{1,2})\b"
    ),
    re.compile(r"(?i)\b(?:yes|haan|ok|okay|yeah|hmm|correct)\s*(\d{1,2})\b"),
    re.compile(r"(?i)\b(\d{1,2})\s*(?:tu|ta)\s+(?:diya|lage|lagibo|dibo|add)"),
    re.compile(r"(?i)\b(\d{1,2})\s*ta\s+(?:diya|add)"),
    re.compile(r"(?i)\boption\s*(\d{1,2})\s*tu\b"),
    re.compile(r"(?i)\b(\d{1,2})\s*number\s*tu\b"),
]
_OPTION_X_RE = re.compile(r"(?i)\b(\d{1,2})\s*x\s*(\d{1,2})\b")


@dataclass(frozen=True)
class ListedOptionReply:
    """0-based index into the pending option list."""

    index: int | None = None
    pack_count: int | None = None
    declined: bool = False


def _valid_index(one_based: int, count: int) -> int | None:
    i = one_based - 1
    if 0 <= i < count:
        return i
    return None


def _pack_from_text(text: str, *, skip_digit: int | None = None) -> int | None:
    raw = text or ""
    if skip_digit is not None:
        raw = re.sub(rf"\b{skip_digit}\b", " ", raw, count=1)
    n = parse_quantity_from_text(raw, default=0)
    return n if n > 1 else None


def parse_listed_option_reply(text: str, option_count: int) -> ListedOptionReply | None:
    """
    Interpret a reply to "Which one? Reply 1, 2, or …".

    Returns None when the message does not look like a list selection.
    """
    if option_count < 1:
        return None
    t = (text or "").strip()
    if not t:
        return None
    if _DECLINE_RE.search(t):
        return ListedOptionReply(declined=True)

    m = _PACK_THEN_OPTION_RE.search(t)
    if m:
        idx = _valid_index(int(m.group("opt")), option_count)
        if idx is not None:
            return ListedOptionReply(
                index=idx, pack_count=max(1, int(m.group("pack")))
            )

    m = _OPTION_THEN_PACK_RE.search(t)
    if m:
        idx = _valid_index(int(m.group("opt")), option_count)
        if idx is not None:
            return ListedOptionReply(
                index=idx, pack_count=max(1, int(m.group("pack")))
            )

    m = _GLUE_INDEX_RE.match(t)
    if m:
        idx = _valid_index(int(m.group(1)), option_count)
        if idx is not None:
            return ListedOptionReply(index=idx)

    om = _ORDINAL_RE.search(t)
    if om:
        idx = _ORDINAL_TO_INDEX.get(om.group(1).lower())
        if idx is not None and idx < option_count:
            packs = _pack_from_text(t)
            return ListedOptionReply(index=idx, pack_count=packs)

    m = _OPTION_X_RE.search(t)
    if m:
        idx = _valid_index(int(m.group(1)), option_count)
        if idx is not None:
            return ListedOptionReply(
                index=idx, pack_count=max(1, int(m.group(2)))
            )

    for pat in _OPTION_DIGIT_RES:
        m = pat.search(t)
        if not m:
            continue
        one_based = int(m.group(1))
        idx = _valid_index(one_based, option_count)
        if idx is not None:
            packs = _pack_from_text(t, skip_digit=one_based)
            return ListedOptionReply(index=idx, pack_count=packs)

    if re.fullmatch(r"\d{1,2}", t):
        idx = _valid_index(int(t), option_count)
        if idx is not None:
            return ListedOptionReply(index=idx)

    return None
