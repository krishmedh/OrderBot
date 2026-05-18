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
from app.domain.models import Product
from app.services.audio_service import AudioService
from app.services.checkout_flow import parse_checkout_payment_method, parse_delivery_details
from app.services.inventory_service import InventoryService
from app.services.orchestrator import CommerceOrchestrator
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.promo_service import PromotionService
from app.services.qa_service import QAService
from app.services.shopping_session import CartLine, ShoppingSessionStore
from app.services.store_inventory_locator import StoreInventoryLocator


@pytest.fixture
def checkout_orch() -> CommerceOrchestrator:
    catalog_root = Path(tempfile.mkdtemp()) / "catalogs"
    catalog_root.mkdir(parents=True)
    inventory_repo = InMemoryInventoryRepository()
    inventory_repo.products["RICE-1KG"] = Product("RICE-1KG", "Rice 1kg", 100, 65.0)
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


def test_parse_delivery_details() -> None:
    assert parse_delivery_details("12 Main St, Guwahati\n9876543210") == (
        "12 Main St Guwahati",
        "+919876543210",
    )
    assert parse_delivery_details("+91 98765 43210, House 5") is None
    assert parse_delivery_details("short 9876543210") is None


def test_parse_payment_method() -> None:
    assert parse_checkout_payment_method("COD") == "cod"
    assert parse_checkout_payment_method("pay online") == "online"


def test_checkout_cod_flow(checkout_orch: CommerceOrchestrator) -> None:
    phone = "919900001111"
    sid = "default"
    sess = checkout_orch._shopping.session(phone, sid)
    sess.cart.append(
        CartLine(sku="RICE-1KG", quantity=1, name="Rice 1kg", unit_price=65.0, line_total=65.0)
    )

    r1 = checkout_orch.shopping_turn(phone, sid, "checkout")
    assert r1 is not None
    assert "delivery address" in r1["reply"].lower()
    assert sess.pending_checkout is not None
    assert sess.pending_checkout.step == "delivery"

    r2 = checkout_orch.shopping_turn(
        phone, sid, "House 12, ABC Colony, Guwahati\n9876543210"
    )
    assert r2 is not None
    assert "COD" in r2["reply"]
    assert sess.pending_checkout.step == "payment"

    r3 = checkout_orch.shopping_turn(phone, sid, "cod")
    assert r3 is not None
    assert "deliver to you shortly" in r3["reply"].lower()
    assert "QR code" in r3["reply"]
    assert r3.get("order_id")
    assert not sess.cart
    assert sess.pending_checkout is None


def test_checkout_online_flow(checkout_orch: CommerceOrchestrator) -> None:
    phone = "919900002222"
    sid = "default"
    sess = checkout_orch._shopping.session(phone, sid)
    sess.cart.append(
        CartLine(sku="RICE-1KG", quantity=2, name="Rice 1kg", unit_price=65.0, line_total=130.0)
    )

    checkout_orch.shopping_turn(phone, sid, "checkout")
    checkout_orch.shopping_turn(phone, sid, "Near Temple Road, Guwahati 781001\n9988776655")
    r = checkout_orch.shopping_turn(phone, sid, "online")
    assert r is not None
    assert "https://pay.local/" in r["reply"]
    assert r.get("order_id")
