"""Map WhatsApp business metadata (phone number id / display number) to ``store_id``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _digits_only(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


def load_store_routing(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"by_phone_number_id": {}, "by_display_phone_digits": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "by_phone_number_id": {str(k): str(v) for k, v in (data.get("by_phone_number_id") or {}).items()},
        "by_display_phone_digits": {str(k): str(v) for k, v in (data.get("by_display_phone_digits") or {}).items()},
    }


def resolve_store_id(metadata: dict[str, Any] | None, routing: dict[str, Any], default_store_id: str) -> str:
    """Resolve store from Meta webhook ``value.metadata``."""
    if not metadata:
        return default_store_id
    phone_number_id = str(metadata.get("phone_number_id") or "").strip()
    if phone_number_id:
        sid = (routing.get("by_phone_number_id") or {}).get(phone_number_id)
        if sid:
            return sid
    display = str(metadata.get("display_phone_number") or "")
    digits = _digits_only(display)
    if digits:
        sid = (routing.get("by_display_phone_digits") or {}).get(digits)
        if sid:
            return sid
    return default_store_id
