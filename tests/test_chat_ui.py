from fastapi.testclient import TestClient

import app.main as main_module

client = TestClient(main_module.app)


def test_chat_page_loads() -> None:
    r = client.get("/chat")
    assert r.status_code == 200
    assert "Store Chat" in r.text
    assert "/chat/assets/app.js" in r.text


def test_root_redirects_to_chat() -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/chat"
