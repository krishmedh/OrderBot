from app.adapters.fake_integrations import FakeQAProvider, FakeWhatsAppGateway
import app.main as main_module
from fastapi.testclient import TestClient

from app.services.qa_service import QAService

app = main_module.app


def test_webhook_question() -> None:
    old_qa = main_module.orchestrator.qa_service
    main_module.orchestrator.qa_service = QAService(FakeQAProvider())
    try:
        client = TestClient(app)
        response = client.post(
            "/webhook/whatsapp",
            json={
                "intent": "question",
                "phone": "+911234567890",
                "message": "Do you have rice?",
                "sku": "RICE-1KG",
            },
        )
        assert response.status_code == 200
        assert "Thank you" in response.json()["reply"]
        body = response.json()["reply"].lower()
        assert "rice" in body and "stock" in body
    finally:
        main_module.orchestrator.qa_service = old_qa


def test_webhook_question_uses_qa_when_no_catalog_hit() -> None:
    old_qa = main_module.orchestrator.qa_service
    main_module.orchestrator.qa_service = QAService(FakeQAProvider())
    try:
        client = TestClient(app)
        response = client.post(
            "/webhook/whatsapp",
            json={
                "intent": "question",
                "phone": "+919988776655",
                "message": "What are your delivery hours tomorrow?",
                "sku": "RICE-1KG",
            },
        )
        assert response.status_code == 200
        body = response.json()["reply"].lower()
        assert "delivery" in body or "thank you" in body
    finally:
        main_module.orchestrator.qa_service = old_qa


def test_webhook_broadcast() -> None:
    main_module.promotion_service.whatsapp_gateway = FakeWhatsAppGateway()
    client = TestClient(app)
    response = client.post(
        "/webhook/whatsapp",
        json={
            "intent": "broadcast",
            "phones": ["+911111111111", "+922222222222"],
            "message": "Weekend offer: 10% off!",
        },
    )
    assert response.status_code == 200
    assert "broadcast" in response.json()["reply"].lower()
