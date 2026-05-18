import pytest

from app.domain.models import Product
from app.services.cart_pricing import (
    compute_cart_line,
    parse_pack_size_grams,
    parse_weight_grams,
)


def _moong() -> Product:
    return Product(
        sku="DAL-MOONG-1KG",
        name="Moong dal 1kg",
        quantity_available=50,
        price=105.0,
    )


def test_parse_weight_and_pack_size() -> None:
    assert parse_weight_grams("5 kg moong dal") == 5000.0
    assert parse_pack_size_grams("Moong dal 1kg", "DAL-MOONG-1KG") == 1000.0


def test_five_kg_moong_line() -> None:
    packs, total, note = compute_cart_line(_moong(), "I need 5 kg moong dal")
    assert packs == 5
    assert total == 525.0
    assert "5 kg" in note


def test_quarter_kg_moong_line() -> None:
    packs, total, note = compute_cart_line(_moong(), "250g moong dal")
    assert packs == 1
    assert total == 26.25
    assert "250 g" in note


def test_pack_count_without_weight() -> None:
    packs, total, note = compute_cart_line(_moong(), "3 moong dal")
    assert packs == 3
    assert total == 315.0
    assert "3 pack" in note


@pytest.mark.parametrize(
    "override, text, expected_packs, expected_total",
    [
        (2, "yes", 2, 210.0),
    ],
)
def test_pack_count_override(
    override: int, text: str, expected_packs: int, expected_total: float
) -> None:
    packs, total, _ = compute_cart_line(
        _moong(), text, pack_count_override=override
    )
    assert packs == expected_packs
    assert total == expected_total
