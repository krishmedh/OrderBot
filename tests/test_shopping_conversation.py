import json
import tempfile
from pathlib import Path

import pytest

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
from app.domain.intent_classification import IntentClassification


class _ShoppingTestIntentClassifier:
    """Keep shopping-dialog tests on local catalogue logic (no live OpenAI)."""

    def classify(self, history, current_message, *, log_context=None):
        return IntentClassification(
            items={},
            confidence=0.0,
            context_used="current",
        )


@pytest.fixture
def north_orch() -> CommerceOrchestrator:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "SUGAR-1KG", "name": "Sugar 1kg", "quantity_available": 80, "price": 45.0},
        {"sku": "DAL-MOONG-1KG", "name": "Moong dal 1kg", "quantity_available": 50, "price": 105.0},
        {"sku": "OIL-MUSTARD-1L", "name": "Mustard oil 1 litre", "quantity_available": 25, "price": 155.0},
        {"sku": "OIL-SUNFLOWER-1L", "name": "Sunflower oil 1 litre", "quantity_available": 30, "price": 165.0},
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
        intent_classifier=_ShoppingTestIntentClassifier(),  # type: ignore[arg-type]
    )


def test_yes_adds_sugar_to_cart(north_orch: CommerceOrchestrator) -> None:
    phone = "+919900000001"
    sid = "north"
    r1 = north_orch.handle(
        {
            "intent": "question",
            "phone": phone,
            "store_id": sid,
            "message": "Do you have 1 kg sugar?",
        }
    )
    assert "yes" in r1["reply"].lower()
    assert "SUGAR" in r1["reply"].upper()
    r2 = north_orch.handle({"intent": "question", "phone": phone, "store_id": sid, "message": "Yes"})
    assert "cart" in r2["reply"].lower()
    assert "45.00" in r2["reply"]


def test_two_mustard_one_litre_packs(north_orch: CommerceOrchestrator) -> None:
    phone = "+919900000003"
    sid = "north"
    north_orch.handle(
        {
            "intent": "question",
            "phone": phone,
            "store_id": sid,
            "message": "I want 1 litre oil",
        }
    )
    r = north_orch.handle(
        {
            "intent": "question",
            "phone": phone,
            "store_id": sid,
            "message": "2 mustard 1 litre",
        }
    )
    assert "310.00" in r["reply"]
    assert "cart" in r["reply"].lower()


def test_yes_with_quantity_override(north_orch: CommerceOrchestrator) -> None:
    phone = "+919900000004"
    sid = "north"
    north_orch.handle(
        {
            "intent": "question",
            "phone": phone,
            "store_id": sid,
            "message": "Do you have sugar?",
        }
    )
    r = north_orch.handle({"intent": "question", "phone": phone, "store_id": sid, "message": "yes 3"})
    assert "× 3" in r["reply"] or "135.00" in r["reply"]


def test_oil_disambiguation_then_mustard(north_orch: CommerceOrchestrator) -> None:
    phone = "+919900000002"
    sid = "north"
    r1 = north_orch.handle(
        {
            "intent": "question",
            "phone": phone,
            "store_id": sid,
            "message": "I want 1 litre oil",
        }
    )
    assert "oil" in r1["reply"].lower()
    assert "mustard" in r1["reply"].lower() or "sunflower" in r1["reply"].lower()
    r2 = north_orch.handle(
        {
            "intent": "question",
            "phone": phone,
            "store_id": sid,
            "message": "get me mustart 1 litre",
        }
    )
    assert "cart" in r2["reply"].lower()
    assert "155.00" in r2["reply"] or "Mustard" in r2["reply"]


def test_weight_based_moong_five_kg(north_orch: CommerceOrchestrator) -> None:
    phone = "+919900000010"
    sid = "north"
    north_orch.handle(
        {
            "intent": "question",
            "phone": phone,
            "store_id": sid,
            "message": "5 kg moong dal",
        }
    )
    r = north_orch.handle({"intent": "question", "phone": phone, "store_id": sid, "message": "yes"})
    assert "525.00" in r["reply"]
    assert "5 kg" in r["reply"].lower() or "5 kg" in r["reply"]


def test_cart_show_remove_update(north_orch: CommerceOrchestrator) -> None:
    phone = "+919900000011"
    sid = "north"
    north_orch.handle(
        {"intent": "question", "phone": phone, "store_id": sid, "message": "sugar"}
    )
    north_orch.handle({"intent": "question", "phone": phone, "store_id": sid, "message": "yes"})
    north_orch.handle(
        {"intent": "question", "phone": phone, "store_id": sid, "message": "moong dal"}
    )
    north_orch.handle({"intent": "question", "phone": phone, "store_id": sid, "message": "yes"})

    show = north_orch.handle({"intent": "question", "phone": phone, "store_id": sid, "message": "cart"})
    assert "Your cart" in show["reply"]
    assert "SUGAR" in show["reply"].upper()
    assert "MOONG" in show["reply"].upper()

    removed = north_orch.handle(
        {"intent": "question", "phone": phone, "store_id": sid, "message": "remove sugar"}
    )
    assert "Removed" in removed["reply"]
    assert "45.00" in removed["reply"] or "0.00" not in removed["reply"]

    updated = north_orch.handle(
        {
            "intent": "question",
            "phone": phone,
            "store_id": sid,
            "message": "update moong dal to 2",
        }
    )
    assert "Updated" in updated["reply"]
    assert "210.00" in updated["reply"]
