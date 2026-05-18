from app.logging_setup import expand_embedded_json_strings, format_json_for_log


def test_format_json_for_log_expands_message_content() -> None:
    inner = '{"language": "en", "items": {"eggs": {"sub_intent": "add_to_cart"}}}'
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": inner,
                }
            }
        ]
    }
    out = format_json_for_log(body)
    assert '"language": "en"' in out
    assert '"sub_intent": "add_to_cart"' in out
    assert "\\n" not in out.split("content")[1][:80]


def test_expand_embedded_json_leaves_plain_text() -> None:
    assert expand_embedded_json_strings("hello") == "hello"
    assert expand_embedded_json_strings('{"a": 1}') == {"a": 1}
