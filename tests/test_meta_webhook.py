import hashlib
import hmac
import json

import app.main as main_module
from fastapi.testclient import TestClient
from app.config import settings


def test_meta_webhook_sends_outbound_message() -> None:
    client = TestClient(main_module.app)
    sent: list[tuple[str, str]] = []

    if hasattr(main_module.whatsapp_gateway, "sent_messages"):
        main_module.whatsapp_gateway.sent_messages.clear()
    else:
        original_send = main_module.whatsapp_gateway.send_message

        def _capture_send(phone: str, text: str) -> None:
            sent.append((phone, text))

        main_module.whatsapp_gateway.send_message = _capture_send  # type: ignore[method-assign]

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
        assert main_module.whatsapp_gateway.sent_messages, "Expected Graph send_message call"
        to, text = main_module.whatsapp_gateway.sent_messages[0]
    else:
        assert sent, "Expected Graph send_message call"
        to, text = sent[0]
        main_module.whatsapp_gateway.send_message = original_send  # type: ignore[method-assign]
    assert to == "919876543210"
    assert "RICE-1KG" in text
