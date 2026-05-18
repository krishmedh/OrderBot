from app.domain.interfaces import OrderRepository, PaymentGateway
from app.domain.models import OrderStatus


class PaymentService:
    def __init__(self, order_repo: OrderRepository, payment_gateway: PaymentGateway) -> None:
        self.order_repo = order_repo
        self.payment_gateway = payment_gateway

    def initiate_payment(self, order_id: str) -> str:
        order = self.order_repo.get(order_id)
        if not order:
            raise ValueError("Order not found.")
        return self.payment_gateway.create_payment_link(order_id, order.total_amount)

    def mark_paid(self, order_id: str) -> None:
        order = self.order_repo.get(order_id)
        if not order:
            raise ValueError("Order not found.")
        order.status = OrderStatus.PAID
        self.order_repo.save(order)
