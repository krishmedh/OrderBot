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
from app.domain.interfaces import QAProvider
from app.domain.intent_classification import IntentClassification


class AlwaysUnknownIntentClassifier:
    """Force conversational QA routing for deterministic history checks."""

    def classify(
        self,
        history: list[tuple[str, str]],
        current_message: str,
        *,
        log_context: dict | None = None,
    ) -> IntentClassification:
        return IntentClassification(
            items={},
            confidence=1.0,
            language="en",
            urgency="LOW",
            context_used="both" if history else "current",
        )


class RecordingQAProvider(QAProvider):
    def __init__(self) -> None:
        self.history_snapshots: list[list[tuple[str, str]]] = []

    def answer(
        self,
        question: str,
        context: str = "",
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        self.history_snapshots.append(list(history) if history else [])
        return "fixed-assistant-reply"


@pytest.fixture
def orchestrator() -> CommerceOrchestrator:
    catalog_root = Path(tempfile.mkdtemp()) / "catalogs"
    catalog_root.mkdir(parents=True)
    inventory_repo = InMemoryInventoryRepository()
    locator = StoreInventoryLocator(catalog_root, "default", fallback=inventory_repo)
    order_repo = InMemoryOrderRepository()
    return CommerceOrchestrator(
        inventory_service=InventoryService(locator),
        order_service=OrderService(locator, order_repo),
        payment_service=PaymentService(order_repo, FakePaymentGateway()),
        qa_service=QAService(FakeQAProvider()),
        audio_service=AudioService(FakeSpeechToTextProvider()),
        promotion_service=PromotionService(FakeWhatsAppGateway()),
    )


@pytest.fixture
def orchestrator_with_recording_qa() -> tuple[CommerceOrchestrator, RecordingQAProvider]:
    catalog_root = Path(tempfile.mkdtemp()) / "catalogs"
    catalog_root.mkdir(parents=True)
    inventory_repo = InMemoryInventoryRepository()
    locator = StoreInventoryLocator(catalog_root, "default", fallback=inventory_repo)
    order_repo = InMemoryOrderRepository()
    recording = RecordingQAProvider()
    orch = CommerceOrchestrator(
        inventory_service=InventoryService(locator),
        order_service=OrderService(locator, order_repo),
        payment_service=PaymentService(order_repo, FakePaymentGateway()),
        qa_service=QAService(recording),
        audio_service=AudioService(FakeSpeechToTextProvider()),
        promotion_service=PromotionService(FakeWhatsAppGateway()),
        intent_classifier=AlwaysUnknownIntentClassifier(),  # type: ignore[arg-type]
    )
    return orch, recording


def test_qa_receives_prior_turns_in_history(
    orchestrator_with_recording_qa: tuple[CommerceOrchestrator, RecordingQAProvider],
) -> None:
    orch, recording = orchestrator_with_recording_qa
    orch.handle(
        {
            "intent": "question",
            "phone": "+919876543210",
            "store_id": "default",
            "message": "What are your delivery hours?",
        }
    )
    orch.handle(
        {
            "intent": "question",
            "phone": "+919876543210",
            "store_id": "default",
            "message": "Do you deliver on Sunday?",
        }
    )
    assert recording.history_snapshots[0] == []
    assert len(recording.history_snapshots[1]) == 1
    assert "delivery hours" in recording.history_snapshots[1][0][0].lower()
    assert recording.history_snapshots[1][0][1] == "fixed-assistant-reply"


def test_availability(orchestrator: CommerceOrchestrator) -> None:
    out = orchestrator.handle({"intent": "availability", "sku": "RICE-1KG"})
    assert "available" in out["reply"]


def test_availability_search(orchestrator: CommerceOrchestrator) -> None:
    out = orchestrator.handle({"intent": "availability_search", "query": "rice"})
    assert "RICE" in out["reply"].upper() or "rice" in out["reply"].lower()


def test_availability_search_natural_sentence(orchestrator: CommerceOrchestrator) -> None:
    out = orchestrator.handle(
        {"intent": "availability_search", "query": "Do you have rice in stock?", "phone": "+1000"}
    )
    assert "RICE" in out["reply"].upper() or "rice" in out["reply"].lower()


def test_question_uses_catalog_when_product_words_match(orchestrator: CommerceOrchestrator) -> None:
    """Dev JSON often sends intent=question; still resolve stock from catalogue tokens."""
    out = orchestrator.handle(
        {
            "intent": "question",
            "phone": "+1000",
            "message": "I'm sorry but is rice in stock at your store?",
        }
    )
    assert "Rice" in out["reply"] or "rice" in out["reply"].lower()
    assert "RICE" in out["reply"].upper()


def test_greeting(orchestrator: CommerceOrchestrator) -> None:
    out = orchestrator.handle({"intent": "greeting", "phone": "+919999999999"})
    assert "Hello" in out["reply"]
    assert "thank" in out["reply"].lower()


def test_place_and_pay(orchestrator: CommerceOrchestrator) -> None:
    order = orchestrator.handle(
        {
            "intent": "place_order",
            "phone": "+919999999999",
            "items": [{"sku": "TEA-500G", "quantity": 1}],
        }
    )
    assert "order_id" in order
    payment = orchestrator.handle({"intent": "pay", "order_id": order["order_id"]})
    assert "https://pay.local/" in payment["reply"]


def test_cancel_order(orchestrator: CommerceOrchestrator) -> None:
    order = orchestrator.handle(
        {
            "intent": "place_order",
            "phone": "+919999999999",
            "items": [{"sku": "RICE-1KG", "quantity": 2}],
        }
    )
    result = orchestrator.handle({"intent": "cancel_order", "order_id": order["order_id"]})
    assert "cancelled" in result["reply"].lower()


def test_audio_flow(orchestrator: CommerceOrchestrator) -> None:
    out = orchestrator.handle({"intent": "audio", "audio_url": "https://audio.local/clip.ogg"})
    assert "transcribed text" in out["transcribed_text"]
    assert "Thank you" in out["reply"]
