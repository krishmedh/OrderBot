from app.domain.intent_classification import IntentClassification, ItemIntent
from app.services.assamese_grocery_lexicon import (
    apply_assamese_lexicon,
    detect_assamese_products,
    detect_product_availability_query,
    mentions_tea_leaves,
)


def test_saa_paat_is_tea_not_soap() -> None:
    assert mentions_tea_leaves("saa paat u laage")
    assert mentions_tea_leaves("muk saa paat aaru sabun laage")
    products = detect_assamese_products("muk saa paat aaru sabun laage")
    keys = {k for k, _ in products}
    assert keys == {"tea leaves", "soap"}


def test_lexicon_fixes_soap_misclassification() -> None:
    wrong = IntentClassification(
        items={
            "soap": ItemIntent(
                sub_intent="modify_item_from_cart",
                quantity="2",
                normalized_query="Add 1 more Lux bathing soap to cart",
            )
        }
    )
    fixed = apply_assamese_lexicon(wrong, "saa paat u laage")
    assert "tea leaves" in fixed.items
    assert "soap" not in fixed.items
    assert fixed.items["tea leaves"].sub_intent == "add_to_cart"


def test_saa_laage_maps_to_tea() -> None:
    products = detect_assamese_products("saa laage")
    assert any(k == "tea leaves" for k, _ in products)


def test_koni_ase_neki_is_eggs_availability_query() -> None:
    assert detect_product_availability_query("koni ase neki") == "eggs"
    wrong = IntentClassification(
        items={
            "catalogue": ItemIntent(
                sub_intent="query_items",
                normalized_query="What products are available",
            )
        }
    )
    fixed = apply_assamese_lexicon(wrong, "koni ase neki")
    assert fixed.items["eggs"].sub_intent == "query_items"
    assert "catalogue" not in fixed.items


def test_twelve_pack_koni_ase_neki_is_availability_not_add() -> None:
    fixed = apply_assamese_lexicon(
        IntentClassification(
            items={
                "eggs": ItemIntent(
                    sub_intent="add_to_cart",
                    quantity="12",
                    normalized_query="Add 12 packs of eggs",
                )
            }
        ),
        "12 pack koni ase neki",
    )
    assert fixed.items["eggs"].sub_intent == "query_items"
    assert "12" in fixed.items["eggs"].quantity


def test_ki_ase_neki_stays_catalogue() -> None:
    assert detect_product_availability_query("ki ase neki") is None
    fixed = apply_assamese_lexicon(
        IntentClassification(items={}), "ki ase neki"
    )
    assert "catalogue" in fixed.items
