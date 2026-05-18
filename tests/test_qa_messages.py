from app.adapters.http_integrations import build_whatsapp_qa_messages


def test_build_whatsapp_qa_messages_includes_history() -> None:
    msgs = build_whatsapp_qa_messages("follow-up", "", [("first question", "first answer")])
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "first question"}
    assert msgs[2] == {"role": "assistant", "content": "first answer"}
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "follow-up"
