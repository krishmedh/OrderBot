import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

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
import app.main as main_module


def test_menu_returns_product_images() -> None:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "SUGAR-1KG", "name": "Sugar 1kg", "quantity_available": 80, "price": 45.0},
        {"sku": "RICE-1KG", "name": "Rice 1kg", "quantity_available": 120, "price": 65.0},
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
    out = orch.handle(
        {"intent": "menu", "phone": "+91", "store_id": "north", "message": "menu"}
    )
    assert "images" in out
    assert len(out["images"]) >= 1
    assert out["images"][0]["url"].startswith("https://")


def test_webhook_dev_menu_includes_images() -> None:
    client = TestClient(main_module.app)
    r = client.post(
        "/webhook/whatsapp",
        json={
            "intent": "question",
            "phone": "+919900000099",
            "store_id": main_module.settings.default_store_id,
            "message": "menu",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("reply")
    assert isinstance(data.get("images"), list)
    if data["images"]:
        assert "url" in data["images"][0]
