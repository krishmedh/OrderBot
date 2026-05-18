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
from app.services.shopping_session import CartLine
from app.services.store_inventory_locator import StoreInventoryLocator


@pytest.fixture
def orch() -> CommerceOrchestrator:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "CLING-FILM", "name": "Cling wrap 30m", "quantity_available": 28, "price": 48.0},
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


def test_add_one_more_increments_pack(orch: CommerceOrchestrator) -> None:
    phone = "+919900000300"
    store_id = "north"
    sess = orch._shopping.session(phone, store_id)
    sess.cart.append(
        CartLine(
            sku="CLING-FILM",
            quantity=2,
            name="Cling wrap 30m",
            unit_price=48.0,
            line_total=96.0,
            weight_note="60m (2 × 30m pack)",
        )
    )
    classification = IntentClassification(
        items={
            "cling wrap": ItemIntent(
                intent="grocery",
                sub_intent="modify_item_from_cart",
                quantity="+1 pack",
                normalized_query="Add one more cling wrap",
            )
        }
    )
    ctx = IntentHandlingContext(
        phone=phone,
        store_id=store_id,
        user_text="add one more cling wrap",
        payload={},
        history=[],
        classification=classification,
        orchestrator=orch,
    )
    result = GroceryActionExecutor().execute(ctx)
    assert result is not None
    assert sess.cart[0].quantity == 3
    assert sess.cart[0].line_total == 144.0
