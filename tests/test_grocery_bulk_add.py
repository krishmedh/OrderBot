import json
import tempfile
from pathlib import Path

import pytest

from app.domain.intent_classification import IntentClassification, ItemIntent
from app.adapters.fake_integrations import (
    FakePaymentGateway,
    FakeQAProvider,
    FakeSpeechToTextProvider,
    FakeWhatsAppGateway,
)
from app.adapters.in_memory_repositories import InMemoryInventoryRepository, InMemoryOrderRepository
from app.services.audio_service import AudioService
from app.services.intent_handlers.base import IntentHandlingContext
from app.services.intent_handlers.grocery_actions import GroceryActionExecutor
from app.services.inventory_service import InventoryService
from app.services.orchestrator import CommerceOrchestrator
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.promo_service import PromotionService
from app.services.qa_service import QAService
from app.services.store_inventory_locator import StoreInventoryLocator


@pytest.fixture
def north_orch() -> CommerceOrchestrator:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "CLING-FILM", "name": "Cling wrap 30m", "quantity_available": 28, "price": 48.0},
        {"sku": "EGGS-6", "name": "Eggs (6 pieces)", "quantity_available": 50, "price": 48.0},
        {"sku": "EGGS-12", "name": "Eggs (12 pieces)", "quantity_available": 30, "price": 92.0},
        {"sku": "MOP", "name": "Floor mop", "quantity_available": 18, "price": 220.0},
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


def test_bulk_add_cling_wrap_eggs_floor_mop(north_orch: CommerceOrchestrator) -> None:
    phone = "+919876543210"
    sid = "north"
    classification = IntentClassification(
        items={
            "cling wrap": ItemIntent(
                sub_intent="add_to_cart",
                quantity="",
                normalized_query="Add cling wrap",
            ),
            "eggs": ItemIntent(
                sub_intent="add_to_cart",
                quantity="12",
                normalized_query="Add 12 packs of eggs",
            ),
            "floor mop": ItemIntent(
                sub_intent="add_to_cart",
                quantity="",
                normalized_query="Add floor mop",
            ),
        }
    )
    ctx = IntentHandlingContext(
        phone=phone,
        store_id=sid,
        user_text="cling wrap, eggs, floor mop",
        payload={},
        history=[],
        classification=classification,
        orchestrator=north_orch,
    )
    result = GroceryActionExecutor().execute(ctx)
    assert result is not None
    sess = north_orch._shopping.session(phone, sid)
    skus = {line.sku for line in sess.cart}
    assert "CLING-FILM" in skus
    assert "EGGS-12" in skus
    assert len(sess.cart) >= 2
    reply = result["reply"].lower()
    assert "cling" in reply
    assert sess.pending_quantity_batch is not None or "MOP" in skus
