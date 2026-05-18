import json
import tempfile
from pathlib import Path

from app.adapters.fake_integrations import (
    FakePaymentGateway,
    FakeQAProvider,
    FakeSpeechToTextProvider,
    FakeWhatsAppGateway,
)
from app.adapters.in_memory_repositories import InMemoryInventoryRepository, InMemoryOrderRepository
from app.domain.intent_classification import IntentClassification, ItemIntent
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


def test_koni_ase_neki_shows_stock_and_asks_quantity() -> None:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "EGGS-6", "name": "Eggs (6 pieces)", "quantity_available": 50, "price": 48.0},
        {"sku": "EGGS-12", "name": "Eggs (12 pieces)", "quantity_available": 30, "price": 92.0},
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
    phone = "+919900000201"
    sid = "north"
    classification = IntentClassification(
        items={
            "eggs": ItemIntent(
                sub_intent="query_items",
                normalized_query="Check if eggs are available",
            )
        }
    )
    ctx = IntentHandlingContext(
        phone=phone,
        store_id=sid,
        user_text="koni ase neki",
        payload={},
        history=[],
        classification=classification,
        orchestrator=orch,
    )
    result = GroceryActionExecutor().execute(ctx)
    assert result is not None
    reply = result["reply"].lower()
    assert "available" in reply or "yes" in reply
    assert "how much" in reply or "which one" in reply
    sess = orch._shopping.session(phone, sid)
    assert sess.pending_quantity_batch is not None or sess.pending_options is not None


def test_biscuits_query_lists_all_matches() -> None:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "BISCUIT-PARLE-G", "name": "Parle-G biscuits 800g", "quantity_available": 70, "price": 55.0},
        {"sku": "BISCUIT-MARIE", "name": "Marie biscuits 250g", "quantity_available": 65, "price": 35.0},
        {"sku": "BISCUIT-OREO", "name": "Oreo biscuits 120g", "quantity_available": 50, "price": 30.0},
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
    classification = IntentClassification(
        items={
            "biscuits": ItemIntent(
                sub_intent="query_items",
                normalized_query="Check if biscuits are available",
            )
        }
    )
    ctx = IntentHandlingContext(
        phone="+919900000202",
        store_id="north",
        user_text="biscuits ?",
        payload={},
        history=[],
        classification=classification,
        orchestrator=orch,
    )
    result = GroceryActionExecutor().execute(ctx)
    assert result is not None
    reply = result["reply"]
    assert "Parle-G" in reply
    assert "Marie" in reply
    assert "Oreo" in reply
    assert "Which one" in reply
