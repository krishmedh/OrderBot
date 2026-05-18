from app.domain.interfaces import InventoryRepository, OrderRepository
from app.domain.models import Order, Product


class InMemoryInventoryRepository(InventoryRepository):
    def __init__(self) -> None:
        self.products = {
            "RICE-1KG": Product("RICE-1KG", "Rice 1kg", 100, 65.0),
            "TEA-500G": Product("TEA-500G", "Tea 500g", 60, 210.0),
        }

    def get_product(self, sku: str) -> Product | None:
        return self.products.get(sku)

    def update_stock(self, sku: str, delta: int) -> None:
        product = self.products[sku]
        product.quantity_available += delta

    def list_products(self) -> list[Product]:
        return list(self.products.values())


class InMemoryOrderRepository(OrderRepository):
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        self.orders[order.order_id] = order

    def get(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)
