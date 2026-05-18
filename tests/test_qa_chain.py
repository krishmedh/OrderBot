from unittest.mock import MagicMock, patch

from app.adapters.fake_integrations import FakeQAProvider
from app.adapters.http_integrations import OllamaQAProvider, OpenAIQAProvider
from app.adapters.qa_chain import OpenAIThenOllamaQA


def test_chain_uses_ollama_when_openai_returns_none() -> None:
    openai = MagicMock(spec=OpenAIQAProvider)
    openai.try_chat.return_value = None
    ollama = MagicMock(spec=OllamaQAProvider)
    ollama.answer.return_value = "Ollama reply"
    fake = FakeQAProvider()

    chain = OpenAIThenOllamaQA(openai, ollama, fake)
    out = chain.answer("Hi", "")

    assert out == "Ollama reply"
    openai.try_chat.assert_called_once_with("Hi", "", None)
    ollama.answer.assert_called_once_with("Hi", "", None)


def test_chain_skips_ollama_when_openai_succeeds() -> None:
    openai = MagicMock(spec=OpenAIQAProvider)
    openai.try_chat.return_value = "OpenAI reply"
    ollama = MagicMock(spec=OllamaQAProvider)
    fake = FakeQAProvider()

    chain = OpenAIThenOllamaQA(openai, ollama, fake)
    out = chain.answer("Hi", "")

    assert out == "OpenAI reply"
    ollama.answer.assert_not_called()


@patch.object(OllamaQAProvider, "answer", return_value="")
def test_chain_uses_fake_when_ollama_empty(mock_ollama_answer: MagicMock) -> None:
    openai = MagicMock(spec=OpenAIQAProvider)
    openai.try_chat.return_value = None
    ollama = OllamaQAProvider("http://127.0.0.1:11434", "llama3.2")
    fake = FakeQAProvider()

    chain = OpenAIThenOllamaQA(openai, ollama, fake)
    out = chain.answer("Do you have rice?", "ctx")

    assert "Thank you" in out
    mock_ollama_answer.assert_called_once()
    assert mock_ollama_answer.call_args[0][:3] == ("Do you have rice?", "ctx", None)
