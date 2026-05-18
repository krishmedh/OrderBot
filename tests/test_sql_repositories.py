from app.adapters.db import create_session_factory
from app.adapters.sql_repositories import SqlInventoryRepository, SqlOrderRepository
from app.domain.models import Order, OrderItem


def test_sql_inventory_and_order_repo_roundtrip() -> None:
    session_factory = create_session_factory("sqlite+pysqlite:///:memory:")
    inventory_repo = SqlInventoryRepository(session_factory)
    order_repo = SqlOrderRepository(session_factory)

    product = inventory_repo.get_product("RICE-1KG")
    assert product is not None
    assert product.quantity_available == 100

    inventory_repo.update_stock("RICE-1KG", -3)
    updated = inventory_repo.get_product("RICE-1KG")
    assert updated is not None
    assert updated.quantity_available == 97

    order = Order(
        order_id="order-1",
        customer_phone="+911111111111",
        items=[OrderItem(sku="RICE-1KG", quantity=3)],
        total_amount=195.0,
    )
    order_repo.save(order)
    fetched = order_repo.get("order-1")
    assert fetched is not None
    assert fetched.order_id == "order-1"
    assert fetched.items[0].sku == "RICE-1KG"
