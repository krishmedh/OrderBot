from app.domain.interfaces import QAProvider


class QAService:
    def __init__(self, qa_provider: QAProvider) -> None:
        self.qa_provider = qa_provider

    def answer_customer_question(
        self,
        message: str,
        context: str = "",
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        return self.qa_provider.answer(message, context=context, history=history)
