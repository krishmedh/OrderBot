import json
import tempfile
from pathlib import Path

import pytest

from app.domain.intent_classification import IntentEntities
from app.services.multi_item_cart import (
    CartItemRequest,
    build_cart_requests_from_entities,
    catalog_pack_size_token,
    clause_to_cart_request,
    customer_quantity_specified,
    implies_single_catalog_pack,
    pair_items_and_quantities,
    quantity_selects_product_variant,
    reply_matches_catalog_pack_size,
    split_comma_separated_cart_message,
)
from app.adapters.fake_integrations import (
    FakePaymentGateway,
    FakeQAProvider,
    FakeSpeechToTextProvider,
    FakeWhatsAppGateway,
)
from app.adapters.in_memory_repositories import InMemoryInventoryRepository, InMemoryOrderRepository
from app.services.audio_service import AudioService
from app.services.inventory_service import InventoryService
from app.services.orchestrator import CommerceOrchestrator
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.promo_service import PromotionService
from app.services.qa_service import QAService
from app.services.store_inventory_locator import StoreInventoryLocator


def test_split_comma_separated() -> None:
    parts = split_comma_separated_cart_message("toor dal 4 kg, lux 2 piece, shampoo 1 bottle")
    assert len(parts) == 3
    assert "toor dal 4 kg" in parts[0]


def test_pair_items_and_quantities() -> None:
    reqs = pair_items_and_quantities(
        ["toor dal", "lux", "shampoo"],
        ["4 kg", "2 piece", "1 bottle"],
    )
    assert len(reqs) == 3
    assert reqs[0].search_phrase == "4 kg toor dal"
    assert reqs[2].item == "shampoo"


def test_build_from_entities() -> None:
    ent = IntentEntities(
        items=["toor dal", "lux"],
        quantities=["4 kg", "2 piece"],
    )
    reqs = build_cart_requests_from_entities(ent, raw_text="ignored")
    assert len(reqs) == 2


def test_pair_preserves_empty_quantity_slot() -> None:
    reqs = pair_items_and_quantities(
        ["butter", "honey", "sunflower"],
        ["250g", "", "1 l"],
    )
    assert len(reqs) == 3
    assert reqs[1].quantity == ""
    assert not customer_quantity_specified(reqs[1])
    assert customer_quantity_specified(reqs[0])


def test_30m_is_valid_quantity() -> None:
    req = clause_to_cart_request("30m")
    assert customer_quantity_specified(req)
    assert reply_matches_catalog_pack_size("30m", "Cling wrap 30m", "CLING-FILM")


def test_cling_wrap_defaults_to_catalogue_pack() -> None:
    assert implies_single_catalog_pack("Cling wrap 30m", "CLING-FILM", "cling wrap")
    assert catalog_pack_size_token("Cling wrap 30m", "CLING-FILM") == "30m"


def test_honey_clause_has_no_quantity() -> None:
    req = clause_to_cart_request("honey")
    assert req.item == "honey"
    assert not customer_quantity_specified(req)


def test_quantity_selects_atta_5kg_variant() -> None:
    assert quantity_selects_product_variant("5 kg", "Wheat flour (atta) 5kg", "ATTA-5KG")
    assert quantity_selects_product_variant("5kg", "Wheat flour (atta) 5kg", "ATTA-5KG")
    assert not quantity_selects_product_variant("5 kg", "Wheat flour (atta) 1kg", "ATTA-1KG")
    assert quantity_selects_product_variant("1 kg", "Wheat flour (atta) 1kg", "ATTA-1KG")


def test_build_from_comma_text() -> None:
    reqs = build_cart_requests_from_entities(
        None,
        raw_text="toor dal 4 kg, lux 2 piece, shampoo 1 bottle",
    )
    assert len(reqs) == 3
    assert clause_to_cart_request("lux 2 piece").search_phrase == "lux 2 piece"


@pytest.fixture
def bulk_orch() -> CommerceOrchestrator:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "DAL-TOOR-1KG", "name": "Toor dal 1kg", "quantity_available": 55, "price": 118.0},
        {"sku": "SOAP-LUX", "name": "Lux bathing soap 125g", "quantity_available": 90, "price": 38.0},
        {"sku": "SHAMPOO-180ML", "name": "Shampoo 180ml", "quantity_available": 45, "price": 155.0},
        {"sku": "BUTTER-100G", "name": "Butter 100g", "quantity_available": 45, "price": 58.0},
        {"sku": "HONEY", "name": "Honey", "quantity_available": 30, "price": 185.0},
        {"sku": "OIL-SUNFLOWER-1L", "name": "Sunflower oil 1 litre", "quantity_available": 30, "price": 165.0},
        {"sku": "CLING-FILM", "name": "Cling wrap 30m", "quantity_available": 28, "price": 48.0},
        {"sku": "RICE-1KG", "name": "Rice 1kg", "quantity_available": 120, "price": 65.0},
        {"sku": "SHAMPOO-180ML", "name": "Shampoo 180ml", "quantity_available": 45, "price": 155.0},
    ]
    (root / "north.json").write_text(json.dumps(catalog), encoding="utf-8")
    locator = StoreInventoryLocator(root, "default", fallback=InMemoryInventoryRepository())
    order_repo = InMemoryOrderRepository()
    return CommerceOrchestrator(
        inventory_service=InventoryService(locator),
        order_service=OrderService(locator, order_repo),
        payment_service=PaymentService(order_repo, FakePaymentGateway()),
        qa_service=QAService(FakeQAProvider()),
        audio_service=AudioService(FakeSpeechToTextProvider()),
        promotion_service=PromotionService(FakeWhatsAppGateway()),
    )


def test_add_three_comma_separated_items(bulk_orch: CommerceOrchestrator) -> None:
    phone = "+919900000099"
    sid = "north"
    msg = "toor dal 4 kg, lux 2 piece, shampoo 1 bottle"
    reqs = build_cart_requests_from_entities(None, raw_text=msg)
    result = bulk_orch.try_add_multiple_cart_items(phone, sid, reqs)
    assert result is not None
    reply = result["reply"]
    assert "Added to your cart" in reply
    assert "Toor dal" in reply
    assert "Lux" in reply
    assert "Shampoo" in reply
    assert "472.00" in reply  # 4 × 118 toor dal
    assert "76.00" in reply  # 2 × 38 lux
    assert "155.00" in reply  # 1 shampoo bottle


def test_missing_honey_quantity_prompts(bulk_orch: CommerceOrchestrator) -> None:
    phone = "+919900000100"
    sid = "north"
    msg = "butter 250g, honey, sunflower 1l"
    reqs = build_cart_requests_from_entities(None, raw_text=msg)
    result = bulk_orch.try_process_cart_requests(phone, sid, reqs)
    assert result is not None
    reply = result["reply"]
    assert "How much" in reply
    assert "honey" in reply.lower()
    assert "Added" in reply
    assert (
        "butter" in reply.lower()
        or "sunflower" in reply.lower()
    )

    follow = bulk_orch.try_process_cart_requests(
        phone,
        sid,
        [],
    )
    assert follow is None
    sess = bulk_orch._shopping.session(phone, sid)
    assert sess.pending_quantity_batch is not None
    done = bulk_orch._fulfill_pending_quantity(sid, sess, "250g")
    assert done is not None
    assert "Honey" in done["reply"] or "honey" in done["reply"].lower()
    assert "Sunflower" in done["reply"]


def test_atta_5kg_disambiguates_from_wheat_flour(bulk_orch: CommerceOrchestrator) -> None:
    root = Path(tempfile.mkdtemp()) / "atta_catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "ATTA-1KG", "name": "Wheat flour (atta) 1kg", "quantity_available": 90, "price": 42.0},
        {"sku": "ATTA-5KG", "name": "Wheat flour (atta) 5kg", "quantity_available": 35, "price": 195.0},
    ]
    (root / "north.json").write_text(json.dumps(catalog), encoding="utf-8")
    locator = StoreInventoryLocator(root, "default", fallback=InMemoryInventoryRepository())
    orch = CommerceOrchestrator(
        inventory_service=InventoryService(locator),
        order_service=OrderService(locator, InMemoryOrderRepository()),
        payment_service=PaymentService(InMemoryOrderRepository(), FakePaymentGateway()),
        qa_service=QAService(FakeQAProvider()),
        audio_service=AudioService(FakeSpeechToTextProvider()),
        promotion_service=PromotionService(FakeWhatsAppGateway()),
    )
    phone = "+919900000102"
    sid = "north"
    req = CartItemRequest(item="wheat flour", quantity="5 kg", search_phrase="wheat flour 5 kg")
    product, amb = orch._resolve_product_for_cart_request(sid, req)
    assert product is not None
    assert product.sku == "ATTA-5KG"
    assert not amb

    result = orch.add_cart_lines(phone, sid, [req])
    assert result is not None
    assert "Wheat flour (atta) 5kg" in result["reply"]
    assert "195.00" in result["reply"]
    assert "several products" not in result["reply"].lower()


def test_cling_wrap_list_then_30m_reply(bulk_orch: CommerceOrchestrator) -> None:
    phone = "+919900000101"
    sid = "north"
    msg = "cling wrap , rice , shampoo"
    reqs = build_cart_requests_from_entities(None, raw_text=msg)
    r1 = bulk_orch.try_process_cart_requests(phone, sid, reqs)
    assert r1 is not None
    assert "How much" not in r1["reply"] or "rice" in r1["reply"].lower()

    sess = bulk_orch._shopping.session(phone, sid)
    if sess.pending_quantity_batch:
        r2 = bulk_orch._fulfill_pending_quantity(sid, sess, "30m")
        assert r2 is not None
        assert "How much" not in r2["reply"]
