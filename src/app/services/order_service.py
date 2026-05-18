import uuid

from app.domain.interfaces import OrderRepository
from app.domain.models import Order, OrderItem, OrderStatus
from app.services.store_inventory_locator import StoreInventoryLocator


class OrderService:
    def __init__(self, locator: StoreInventoryLocator, order_repo: OrderRepository) -> None:
        self._locator = locator
        self.order_repo = order_repo

    def place_order(
        self,
        store_id: str | None,
        customer_phone: str,
        items: list[OrderItem],
        *,
        delivery_address: str = "",
        delivery_phone: str = "",
        payment_method: str = "",
    ) -> Order:
        inventory_repo = self._locator.get(store_id)
        total = 0.0
        for item in items:
            product = inventory_repo.get_product(item.sku)
            if not product:
                raise ValueError(f"Unknown product: {item.sku}")
            if product.quantity_available < item.quantity:
                raise ValueError(f"Insufficient stock for: {item.sku}")
            total += product.price * item.quantity

        for item in items:
            inventory_repo.update_stock(item.sku, -item.quantity)

        metadata: dict[str, str] = {}
        if delivery_address.strip():
            metadata["delivery_address"] = delivery_address.strip()
        if delivery_phone.strip():
            metadata["delivery_phone"] = delivery_phone.strip()
        if payment_method.strip():
            metadata["payment_method"] = payment_method.strip()

        order = Order(
            order_id=str(uuid.uuid4()),
            customer_phone=customer_phone,
            items=items,
            total_amount=total,
            store_id=store_id,
            metadata=metadata,
        )
        self.order_repo.save(order)
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self.order_repo.get(order_id)
        if not order:
            raise ValueError("Order not found.")
        if order.status == OrderStatus.CANCELLED:
            return order

        inventory_repo = self._locator.get(order.store_id)
        for item in order.items:
            inventory_repo.update_stock(item.sku, item.quantity)

        order.status = OrderStatus.CANCELLED
        self.order_repo.save(order)
        return order
