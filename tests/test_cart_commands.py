from app.domain.models import Product
from app.services.cart_commands import (
    find_cart_line_index,
    parse_remove_target,
    parse_update_command,
    wants_clear_cart,
    wants_show_cart,
)
from app.services.shopping_session import CartLine


def _cart() -> list[CartLine]:
    return [
        CartLine(sku="DAL-MOONG-1KG", quantity=2, name="Moong dal 1kg", unit_price=105.0),
        CartLine(sku="SUGAR-1KG", quantity=1, name="Sugar 1kg", unit_price=45.0),
    ]


def _products() -> dict[str, Product]:
    return {
        "DAL-MOONG-1KG": Product("DAL-MOONG-1KG", "Moong dal 1kg", 50, 105.0),
        "SUGAR-1KG": Product("SUGAR-1KG", "Sugar 1kg", 80, 45.0),
    }


def test_wants_show_and_clear_cart() -> None:
    assert wants_show_cart("cart")
    assert wants_show_cart("My Cart")
    assert wants_clear_cart("clear cart")


def test_parse_remove_and_update() -> None:
    assert parse_remove_target("remove moong dal") == "moong dal"
    assert parse_update_command("update sugar to 3") == ("sugar", "3")
    assert parse_update_command("update moong dal to 5 kg") == ("moong dal", "5 kg")


def test_find_cart_line_index() -> None:
    cart = _cart()
    products = _products()
    assert find_cart_line_index(cart, "SUGAR-1KG", products) == 1
    assert find_cart_line_index(cart, "moong", products) == 0
    assert find_cart_line_index(cart, "unknown", products) is None
