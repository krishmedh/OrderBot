from app.domain.intent_classification import ItemIntent
from app.services.intent_classifier import HeuristicIntentClassifier, _parse_classification_dict
from app.services.intent_prompt_context import format_cart_state_for_prompt, looks_like_cart_increment
from app.services.shopping_session import CartLine


def test_format_cart_state_empty() -> None:
    assert format_cart_state_for_prompt([]) == "(cart is empty)"


def test_format_cart_state_numbered_lines() -> None:
    cart = [
        CartLine(
            sku="CLING-FILM",
            quantity=1,
            name="Cling wrap 30m",
            unit_price=48.0,
            line_total=48.0,
            weight_note="30m",
        ),
    ]
    text = format_cart_state_for_prompt(cart, currency="INR")
    assert "1. Cling wrap 30m" in text
    assert "Cart total: 48.00 INR" in text


def test_parse_per_item_classification() -> None:
    data = {
        "language": "en",
        "urgency": "LOW",
        "items": {
            "eggs": {
                "intent": "grocery",
                "sub_intent": "add_to_cart",
                "quantity": "2",
                "normalized_query": "Add eggs",
            },
            "sugar": {
                "intent": "grocery",
                "sub_intent": "remove_from_cart",
                "quantity": "",
                "normalized_query": "Remove sugar",
            },
        },
    }
    parsed = _parse_classification_dict(data)
    assert parsed is not None
    assert parsed.items["eggs"].sub_intent == "add_to_cart"
    assert parsed.items["sugar"].sub_intent == "remove_from_cart"


def test_heuristic_comma_list() -> None:
    clf = HeuristicIntentClassifier()
    result = clf.classify([], "cling wrap, honey, eggs")
    assert set(result.items.keys()) == {"cling wrap", "honey", "eggs"}
    assert all(v.sub_intent == "add_to_cart" for v in result.items.values())


def test_heuristic_modify() -> None:
    clf = HeuristicIntentClassifier()
    result = clf.classify([], "update cling wrap to 60m")
    assert "cling wrap" in result.items
    assert result.items["cling wrap"].sub_intent == "modify_item_from_cart"


def test_looks_like_cart_increment() -> None:
    assert looks_like_cart_increment("add one more cling wrap")
