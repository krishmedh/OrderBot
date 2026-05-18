from typing import Any

from pydantic import BaseModel


class WhatsAppEvent(BaseModel):
    intent: str = "question"
    phone: str | None = None
    store_id: str | None = None
    message: str | None = None
    customer_text: str | None = None
    sku: str | None = None
    query: str | None = None
    items: list[dict[str, Any]] | None = None
    order_id: str | None = None
    audio_url: str | None = None
    phones: list[str] | None = None
    skip_intent_classification: bool = False
