from unittest.mock import MagicMock, patch

from app.adapters.http_integrations import OpenAIQAProvider, _openai_qa_fallback


def test_openai_qa_fallback_uses_context() -> None:
    text = _openai_qa_fallback("hi", "SKU X: 5 in stock")
    assert "catalogue" in text.lower()
    assert "SKU X" in text


@patch("app.adapters.http_integrations.time.sleep", lambda *_: None)
@patch("app.adapters.http_integrations.httpx.post")
def test_openai_qa_retries_429_then_succeeds(mock_post: MagicMock) -> None:
    bad = MagicMock()
    bad.status_code = 429
    bad.headers = {"retry-after": "0"}
    bad.is_success = False
    good = MagicMock()
    good.status_code = 200
    good.is_success = True
    good.json.return_value = {"choices": [{"message": {"content": "  Hello there  "}}]}
    mock_post.side_effect = [bad, good]

    p = OpenAIQAProvider("test-key")
    out = p.answer("What is open?", context="")

    assert out == "Hello there"
    assert mock_post.call_count == 2


@patch("app.adapters.http_integrations.time.sleep", lambda *_: None)
@patch("app.adapters.http_integrations.httpx.post")
def test_openai_qa_all_429_returns_fallback(mock_post: MagicMock) -> None:
    bad = MagicMock()
    bad.status_code = 429
    bad.headers = {}
    bad.is_success = False
    mock_post.return_value = bad

    p = OpenAIQAProvider("test-key")
    out = p.answer("Need help", context="")

    assert "rate limit" in out.lower() or "unavailable" in out.lower()
    assert mock_post.call_count == 4


@patch("app.adapters.http_integrations.time.sleep", lambda *_: None)
@patch("app.adapters.http_integrations.httpx.post")
def test_openai_try_chat_all_429_returns_none(mock_post: MagicMock) -> None:
    bad = MagicMock()
    bad.status_code = 429
    bad.headers = {}
    bad.is_success = False
    mock_post.return_value = bad

    p = OpenAIQAProvider("test-key")
    assert p.try_chat("x", "") is None
