import json
import tempfile
from pathlib import Path

import pytest

from app.adapters.in_memory_repositories import InMemoryInventoryRepository
from app.services.inventory_service import InventoryService
from app.services.orchestrator import CommerceOrchestrator
from app.services.store_inventory_locator import StoreInventoryLocator
from app.adapters.fake_integrations import FakePaymentGateway, FakeQAProvider, FakeSpeechToTextProvider, FakeWhatsAppGateway
from app.adapters.in_memory_repositories import InMemoryOrderRepository
from app.services.audio_service import AudioService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.promo_service import PromotionService
from app.services.qa_service import QAService


@pytest.fixture
def north_inventory() -> InventoryService:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "TURMERIC-200G", "name": "Turmeric powder 200g", "quantity_available": 65, "price": 48.0},
        {"sku": "CHOCOLATE-200G", "name": "Chocolate bar 200g", "quantity_available": 40, "price": 95.0},
    ]
    (root / "north.json").write_text(json.dumps(catalog), encoding="utf-8")
    locator = StoreInventoryLocator(root, "default", fallback=InMemoryInventoryRepository())
    return InventoryService(locator)


def test_200g_alone_does_not_match_all_200g_products(north_inventory: InventoryService) -> None:
    matches = north_inventory.catalog_matches("north", "200g")
    assert matches == []


def test_chocolate_request_matches_chocolate_not_turmeric(north_inventory: InventoryService) -> None:
    matches = north_inventory.catalog_matches("north", "I want 200g choclate")
    assert len(matches) == 1
    assert matches[0].sku == "CHOCOLATE-200G"


def test_fuzzy_typo_and_spacing() -> None:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    (root / "north.json").write_text(
        json.dumps(
            [
                {
                    "sku": "BISCUIT-PARLE-G",
                    "name": "Parle-G biscuits 800g",
                    "quantity_available": 70,
                    "price": 55.0,
                },
                {
                    "sku": "BISCUIT-OREO",
                    "name": "Oreo biscuits 120g",
                    "quantity_available": 50,
                    "price": 30.0,
                },
            ]
        ),
        encoding="utf-8",
    )
    locator = StoreInventoryLocator(root, "default", fallback=InMemoryInventoryRepository())
    inv = InventoryService(locator)
    # spacing / missing hyphen
    m = inv.catalog_matches("north", "parle g 3 pkt")
    assert len(m) == 1 and m[0].sku == "BISCUIT-PARLE-G"
    # typo in brand
    m2 = inv.catalog_matches("north", "parleg biscuit")
    assert len(m2) == 1 and m2[0].sku == "BISCUIT-PARLE-G"


def test_hyphenated_brand_name_not_treated_as_sku() -> None:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    (root / "north.json").write_text(
        json.dumps(
            [
                {
                    "sku": "BISCUIT-PARLE-G",
                    "name": "Parle-G biscuits 800g",
                    "quantity_available": 70,
                    "price": 55.0,
                }
            ]
        ),
        encoding="utf-8",
    )
    locator = StoreInventoryLocator(root, "default", fallback=InMemoryInventoryRepository())
    inv = InventoryService(locator)
    for phrase in (
        "parle-g biscuits",
        "parle-g biscuits 3 pkts",
        "Parle-G more 3 pkts",
        "aaru laage parle-g",
    ):
        matches = inv.catalog_matches("north", phrase)
        assert len(matches) == 1, phrase
        assert matches[0].sku == "BISCUIT-PARLE-G"


def test_unknown_product_gets_not_found_reply() -> None:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    (root / "north.json").write_text(
        json.dumps([{"sku": "TURMERIC-200G", "name": "Turmeric powder 200g", "quantity_available": 65, "price": 48.0}]),
        encoding="utf-8",
    )
    locator = StoreInventoryLocator(root, "default", fallback=InMemoryInventoryRepository())
    orch = CommerceOrchestrator(
        inventory_service=InventoryService(locator),
        order_service=OrderService(locator, InMemoryOrderRepository()),
        payment_service=PaymentService(InMemoryOrderRepository(), FakePaymentGateway()),
        qa_service=QAService(FakeQAProvider()),
        audio_service=AudioService(FakeSpeechToTextProvider()),
        promotion_service=PromotionService(FakeWhatsAppGateway()),
    )
    out = orch.handle(
        {
            "intent": "question",
            "phone": "+919900000099",
            "store_id": "north",
            "message": "I want 200g chocolate",
        }
    )
    assert "do not have" in out["reply"].lower()
    assert "turmeric" not in out["reply"].lower()
