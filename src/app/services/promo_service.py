from app.domain.interfaces import WhatsAppGateway


class PromotionService:
    def __init__(self, whatsapp_gateway: WhatsAppGateway) -> None:
        self.whatsapp_gateway = whatsapp_gateway

    def broadcast(self, customer_phones: list[str], message: str) -> None:
        self.whatsapp_gateway.send_broadcast(customer_phones, message)
