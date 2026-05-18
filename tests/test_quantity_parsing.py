import pytest

from app.services.shopping_session import parse_quantity_from_text, parse_shopping_confirmation


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2 mustard 1 litre", 2),
        ("get me 3 sunflower oil", 3),
        ("give us 5 rice 1kg", 5),
        ("4 x sugar 1kg", 4),
        ("2 packets of mustard oil", 2),
        ("1 kg sugar", 1),
        ("10 rice 1kg", 10),
        ("two mustard 1 litre", 2),
        ("three bottles oil", 3),
        ("order 6 milk 1 litre", 6),
        ("1 litre oil only", 1),
        ("I want 200g chocolate", 99),  # no pack count → default
        ("get me mustart 1 litre", 1),
    ],
)
def test_parse_quantity_from_text(text: str, expected: int) -> None:
    assert parse_quantity_from_text(text, default=99) == expected


def test_parse_quantity_default_when_no_signal() -> None:
    assert parse_quantity_from_text("hello there", default=7) == 7


@pytest.mark.parametrize(
    "text,is_conf,override",
    [
        ("Yes", True, None),
        ("ok please", True, None),
        ("yes 4", True, 4),
        ("Yeah 12", True, 12),
        ("maybe", False, None),
    ],
)
def test_parse_shopping_confirmation(text: str, is_conf: bool, override: int | None) -> None:
    c, o = parse_shopping_confirmation(text)
    assert c is is_conf
    assert o == override
