from abc import ABC, abstractmethod
from typing import Iterable, Optional

from app.domain.models import Order, Product


class InventoryRepository(ABC):
    @abstractmethod
    def get_product(self, sku: str) -> Optional[Product]:
        raise NotImplementedError

    @abstractmethod
    def update_stock(self, sku: str, delta: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_products(self) -> list[Product]:
        raise NotImplementedError


class OrderRepository(ABC):
    @abstractmethod
    def save(self, order: Order) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, order_id: str) -> Optional[Order]:
        raise NotImplementedError


class WhatsAppGateway(ABC):
    @abstractmethod
    def send_message(
        self,
        phone: str,
        text: str,
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        raise NotImplementedError

    def send_image(
        self,
        phone: str,
        image_url: str,
        caption: str = "",
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        """Optional: send an image message (default no-op for simple gateways)."""
        return None

    def mark_read_and_show_typing(
        self,
        message_id: str,
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        """Optional: mark inbound message read and show WhatsApp typing indicator."""
        return None

    @abstractmethod
    def send_broadcast(self, phones: Iterable[str], text: str) -> None:
        raise NotImplementedError


class PaymentGateway(ABC):
    @abstractmethod
    def create_payment_link(self, order_id: str, amount: float) -> str:
        raise NotImplementedError


class SpeechToTextProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_url: str) -> str:
        raise NotImplementedError


class QAProvider(ABC):
    @abstractmethod
    def answer(
        self,
        question: str,
        context: str = "",
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        raise NotImplementedError
