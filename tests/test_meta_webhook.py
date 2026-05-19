import hashlib
import hmac
import json

import app.main as main_module
from fastapi.testclient import TestClient
from app.config import settings


def test_meta_webhook_verify_challenge() -> None:
    client = TestClient(main_module.app)
    response = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.whatsapp_verify_token,
            "hub.challenge": "2089357436",
        },
    )
    assert response.status_code == 200
    assert response.text == "2089357436"

    bad = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "2089357436",
        },
    )
    assert bad.status_code == 403


def test_meta_webhook_sends_outbound_message(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_typing_indicator", True)
    client = TestClient(main_module.app)
    sent: list[tuple[str, str]] = []
    typing_calls: list[tuple[str, str | None]] = []

    if hasattr(main_module.whatsapp_gateway, "sent_messages"):
        main_module.whatsapp_gateway.sent_messages.clear()
        if hasattr(main_module.whatsapp_gateway, "typing_indicators"):
            main_module.whatsapp_gateway.typing_indicators.clear()
    else:
        original_send = main_module.whatsapp_gateway.send_message
        original_typing = main_module.whatsapp_gateway.mark_read_and_show_typing

        def _capture_send(phone: str, text: str, **kwargs) -> None:
            sent.append((phone, text))

        def _capture_typing(message_id: str, **kwargs) -> None:
            typing_calls.append((message_id, kwargs.get("from_phone_number_id")))

        main_module.whatsapp_gateway.send_message = _capture_send  # type: ignore[method-assign]
        main_module.whatsapp_gateway.mark_read_and_show_typing = _capture_typing  # type: ignore[method-assign]

    body = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+15550001122",
                                "phone_number_id": "123456789",
                            },
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.test",
                                    "type": "text",
                                    "text": {"body": "stock RICE-1KG"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    raw = json.dumps(body).encode("utf-8")
    secret = settings.meta_app_secret or settings.webhook_verify_secret
    headers = {}
    if secret:
        digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        headers["x-hub-signature-256"] = f"sha256={digest}"

    response = client.post("/webhook/whatsapp", content=raw, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    if hasattr(main_module.whatsapp_gateway, "sent_messages"):
        assert main_module.whatsapp_gateway.typing_indicators, "Expected typing indicator call"
        typing_id, typing_pnid = main_module.whatsapp_gateway.typing_indicators[0]
        assert typing_id == "wamid.test"
        assert typing_pnid == "123456789"
        assert main_module.whatsapp_gateway.sent_messages, "Expected Graph send_message call"
        to, text = main_module.whatsapp_gateway.sent_messages[0]
    else:
        assert typing_calls, "Expected typing indicator call"
        assert typing_calls[0] == ("wamid.test", "123456789")
        assert sent, "Expected Graph send_message call"
        to, text = sent[0]
        main_module.whatsapp_gateway.send_message = original_send  # type: ignore[method-assign]
        main_module.whatsapp_gateway.mark_read_and_show_typing = original_typing  # type: ignore[method-assign]
    assert to == "919876543210"
    assert "RICE-1KG" in text
