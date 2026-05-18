from app.adapters.store_routing import resolve_store_id


def test_resolve_by_phone_number_id() -> None:
    routing = {"by_phone_number_id": {"111": "store_x"}, "by_display_phone_digits": {}}
    meta = {"phone_number_id": "111", "display_phone_number": "+1 555 000 0000"}
    assert resolve_store_id(meta, routing, "default") == "store_x"


def test_resolve_by_display_digits() -> None:
    routing = {"by_phone_number_id": {}, "by_display_phone_digits": {"15550001122": "store_y"}}
    meta = {"display_phone_number": "+1 (555) 000-1122"}
    assert resolve_store_id(meta, routing, "default") == "store_y"


def test_resolve_fallback() -> None:
    routing = {"by_phone_number_id": {}, "by_display_phone_digits": {}}
    assert resolve_store_id({}, routing, "default") == "default"
