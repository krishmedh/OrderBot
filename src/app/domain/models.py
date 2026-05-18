from dataclasses import dataclass, field
from enum import Enum
from typing import List


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


@dataclass
class Product:
    sku: str
    name: str
    quantity_available: int
    price: float
    image_url: str | None = None


@dataclass
class OrderItem:
    sku: str
    quantity: int


@dataclass
class Order:
    order_id: str
    customer_phone: str
    items: List[OrderItem]
    total_amount: float
    status: OrderStatus = OrderStatus.PENDING
    metadata: dict = field(default_factory=dict)
    store_id: str | None = None
