from fastapi.testclient import TestClient

import app.main as main_module

app = main_module.app


def test_menu_via_message_only() -> None:
    client = TestClient(app)
    r = client.post(
        "/webhook/whatsapp",
        json={"message": "menu", "store_id": "store_north", "phone": "+911111111111"},
    )
    assert r.status_code == 200
    body = r.json()["reply"]
    assert "Menu" in body
    assert "Milk" in body or "Sugar" in body


def test_menu_via_question_intent() -> None:
    client = TestClient(app)
    r = client.post(
        "/webhook/whatsapp",
        json={
            "intent": "question",
            "message": "menu",
            "store_id": "store_north",
            "phone": "+922222222222",
        },
    )
    assert r.status_code == 200
    assert "Menu" in r.json()["reply"]
