"""In-memory per-customer chat turns for follow-up questions (keyed by store + phone)."""

from __future__ import annotations

import threading


def conversation_memory_key(phone: str, store_id: str) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    sid = (store_id or "default").strip() or "default"
    if digits:
        return f"{sid}|{digits}"
    return f"{sid}|anonymous"


class ConversationStore:
    """Stores recent (user message, assistant reply) pairs per WhatsApp customer and store."""

    def __init__(self, max_pairs: int = 12) -> None:
        self._max_pairs = max(1, max_pairs)
        self._lock = threading.Lock()
        self._pairs: dict[str, list[tuple[str, str]]] = {}

    def history(self, phone: str, store_id: str) -> list[tuple[str, str]]:
        key = conversation_memory_key(phone, store_id)
        with self._lock:
            return list(self._pairs.get(key, []))

    def append(self, phone: str, store_id: str, user_text: str, assistant_text: str) -> None:
        u = (user_text or "").strip()
        a = (assistant_text or "").strip()
        if not u or not a:
            return
        key = conversation_memory_key(phone, store_id)
        with self._lock:
            lst = self._pairs.setdefault(key, [])
            lst.append((u, a))
            overflow = len(lst) - self._max_pairs
            if overflow > 0:
                del lst[:overflow]
