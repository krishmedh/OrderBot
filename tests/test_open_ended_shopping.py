from app.services.intent_classifier import HeuristicIntentClassifier
from app.services.shopping_intent_signals import looks_like_open_ended_shopping_without_product


def test_household_message_is_vague_signal() -> None:
    assert looks_like_open_ended_shopping_without_product(
        "I want some items for my household"
    )


def test_heuristic_classifier_gives_general_shopping_help() -> None:
    h = HeuristicIntentClassifier()
    out = h.classify([], "I want some items for my household", log_context={})
    assert out.sub_intent == "general_enquiry"
    assert out.intent == "GROCERY_PURCHASE"
