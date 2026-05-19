from typing import Iterable

from app.domain.interfaces import PaymentGateway, QAProvider, SpeechToTextProvider, WhatsAppGateway


class FakeWhatsAppGateway(WhatsAppGateway):
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str]] = []
        self.sent_images: list[tuple[str, str, str]] = []
        self.broadcasts: list[tuple[list[str], str]] = []
        self.typing_indicators: list[tuple[str, str | None]] = []

    def send_message(
        self,
        phone: str,
        text: str,
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        self.sent_messages.append((phone, text))

    def send_image(
        self,
        phone: str,
        image_url: str,
        caption: str = "",
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        self.sent_images.append((phone, image_url, caption))

    def mark_read_and_show_typing(
        self,
        message_id: str,
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        self.typing_indicators.append((message_id, from_phone_number_id))

    def send_broadcast(self, phones: Iterable[str], text: str) -> None:
        self.broadcasts.append((list(phones), text))


class FakePaymentGateway(PaymentGateway):
    def create_payment_link(self, order_id: str, amount: float) -> str:
        return f"https://pay.local/{order_id}?amount={amount}"


class FakeSpeechToTextProvider(SpeechToTextProvider):
    def transcribe(self, audio_url: str) -> str:
        # Placeholder multilingual transcription output.
        return f"transcribed text from {audio_url}"


class FakeQAProvider(QAProvider):
    def answer(
        self,
        question: str,
        context: str = "",
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        q = (question or "").strip()
        if not q:
            return (
                "Thank you for your message. "
                "Please tell us what you would like to know about our products, availability, or your order."
            )
        if context:
            return (
                "Thank you for your inquiry.\n\n"
                "Here is the information we currently have from our catalogue:\n"
                f"{context}\n\n"
                "If you would like to place an order, reply with: order <SKU> <quantity>. "
                "For anything else, describe what you need and we will assist you."
            )
        return (
            "Thank you for reaching out.\n\n"
            "To help you quickly, please mention the product name or SKU, or ask a specific question "
            "about availability, pricing, or delivery.\n\n"
            f'For reference, your message was: "{q}"'
        )
