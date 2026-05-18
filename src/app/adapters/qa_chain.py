import logging

from app.adapters.fake_integrations import FakeQAProvider
from app.adapters.http_integrations import OllamaQAProvider, OpenAIQAProvider
from app.domain.interfaces import QAProvider

logger = logging.getLogger(__name__)


class OpenAIThenOllamaQA(QAProvider):
    """Try OpenAI first; on failure or empty reply, use Ollama; if Ollama also fails, use fake templates."""

    def __init__(
        self,
        openai: OpenAIQAProvider,
        ollama: OllamaQAProvider,
        fake: FakeQAProvider,
    ) -> None:
        self._openai = openai
        self._ollama = ollama
        self._fake = fake

    def answer(
        self,
        question: str,
        context: str = "",
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        primary = self._openai.try_chat(question, context, history)
        if primary:
            return primary
        logger.info("OpenAI QA unavailable; using Ollama fallback")
        secondary = self._ollama.answer(question, context, history)
        if secondary and secondary.strip():
            return secondary
        return self._fake.answer(question, context, history)
