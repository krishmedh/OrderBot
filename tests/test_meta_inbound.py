from app.adapters.meta_inbound import message_to_orchestrator_payload


def test_text_maps_to_greeting() -> None:
    payload = message_to_orchestrator_payload(
        "919876543210",
        {"type": "text", "text": {"body": "hello"}},
        "store_a",
    )
    assert payload["intent"] == "greeting"
    assert payload["store_id"] == "store_a"
    assert payload.get("customer_text") == "hello"


def test_text_maps_to_availability() -> None:
    payload = message_to_orchestrator_payload(
        "919876543210",
        {"type": "text", "text": {"body": "Is stock RICE-1KG available?"}},
        "store_a",
    )
    assert payload["intent"] == "availability"
    assert payload["sku"] == "RICE-1KG"


def test_text_maps_to_availability_search() -> None:
    payload = message_to_orchestrator_payload(
        "919876543210",
        {"type": "text", "text": {"body": "Do you have rice in stock?"}},
        "store_a",
    )
    assert payload["intent"] == "availability_search"
    assert "rice" in payload["query"].lower()


def test_text_maps_to_order() -> None:
    payload = message_to_orchestrator_payload(
        "919876543210",
        {"type": "text", "text": {"body": "order TEA-500G 1"}},
        "store_a",
    )
    assert payload["intent"] == "place_order"
    assert payload["items"][0]["sku"] == "TEA-500G"
    assert payload["items"][0]["quantity"] == 1
