import json

from sqlalchemy.orm import sessionmaker

from app.adapters.db import OrderTable, ProductTable
from app.domain.interfaces import InventoryRepository, OrderRepository
from app.domain.models import Order, OrderItem, OrderStatus, Product


class SqlInventoryRepository(InventoryRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory
        self._seed_products()

    def _seed_products(self) -> None:
        with self.session_factory() as session:
            if session.query(ProductTable).count() == 0:
                session.add_all(
                    [
                        ProductTable(sku="RICE-1KG", name="Rice 1kg", quantity_available=100, price=65.0),
                        ProductTable(sku="TEA-500G", name="Tea 500g", quantity_available=60, price=210.0),
                    ]
                )
                session.commit()

    def get_product(self, sku: str) -> Product | None:
        with self.session_factory() as session:
            row = session.get(ProductTable, sku)
            if not row:
                return None
            return Product(row.sku, row.name, row.quantity_available, row.price)

    def update_stock(self, sku: str, delta: int) -> None:
        with self.session_factory() as session:
            row = session.get(ProductTable, sku)
            if not row:
                raise ValueError(f"Unknown product: {sku}")
            row.quantity_available += delta
            session.commit()

    def list_products(self) -> list[Product]:
        with self.session_factory() as session:
            rows = session.query(ProductTable).all()
            return [Product(r.sku, r.name, r.quantity_available, r.price) for r in rows]


class SqlOrderRepository(OrderRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def save(self, order: Order) -> None:
        items_payload = [{"sku": item.sku, "quantity": item.quantity} for item in order.items]
        with self.session_factory() as session:
            row = session.get(OrderTable, order.order_id)
            if not row:
                row = OrderTable(
                    order_id=order.order_id,
                    customer_phone=order.customer_phone,
                    items_json=json.dumps(items_payload),
                    total_amount=order.total_amount,
                    status=order.status.value,
                    store_id=order.store_id,
                )
                session.add(row)
            else:
                row.customer_phone = order.customer_phone
                row.items_json = json.dumps(items_payload)
                row.total_amount = order.total_amount
                row.status = order.status.value
                row.store_id = order.store_id
            session.commit()

    def get(self, order_id: str) -> Order | None:
        with self.session_factory() as session:
            row = session.get(OrderTable, order_id)
            if not row:
                return None
            items = [OrderItem(sku=i["sku"], quantity=i["quantity"]) for i in json.loads(row.items_json)]
            return Order(
                order_id=row.order_id,
                customer_phone=row.customer_phone,
                items=items,
                total_amount=row.total_amount,
                status=OrderStatus(row.status),
                store_id=row.store_id,
            )
