from app.domain.models import Product
from app.services.cart_commands import parse_update_command
from app.services.cart_pricing import compute_cart_line, parse_length_meters, parse_pack_length_meters


def test_parse_length_meters() -> None:
    assert parse_length_meters("60m") == 60.0
    assert parse_length_meters("update cling wrap to 60 m") == 60.0
    assert parse_pack_length_meters("Cling wrap 30m", "CLING-FILM") == 30.0


def test_cling_wrap_60m_is_two_rolls() -> None:
    p = Product("CLING-FILM", "Cling wrap 30m", 28, 48.0)
    packs, total, note = compute_cart_line(p, "60m")
    assert packs == 2
    assert total == 96.0
    assert "60 m" in note
    assert "2" in note


def test_update_command_parses_60m() -> None:
    assert parse_update_command("update cling wrap to 60m") == ("cling wrap", "60m")
