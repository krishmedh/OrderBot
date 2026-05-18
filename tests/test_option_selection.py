import pytest

from app.services.option_selection import parse_listed_option_reply


@pytest.mark.parametrize(
    "text,expected_index,pack",
    [
        ("1", 0, None),
        ("2.", 1, None),
        ("3 plz", 2, None),
        ("1 please", 0, None),
        ("option 2", 1, None),
        ("go with 3", 2, None),
        ("take 1", 0, None),
        ("first one", 0, None),
        ("second one", 1, None),
        ("prothom tu", 0, None),
        ("ditiyo tu", 1, None),
        ("1 tu diya", 0, None),
        ("2 tu lagibo", 1, None),
        ("1 ta diya", 0, None),
        ("yes 2", 1, None),
        ("haan 3", 2, None),
        ("2 packet 1 number", 0, 2),
        ("1 x 2", 0, 2),
        ("2tu", 1, None),
        ("give me option 2", 1, None),
        ("i need 3", 2, None),
    ],
)
def test_option_selection_patterns(text: str, expected_index: int, pack: int | None) -> None:
    sel = parse_listed_option_reply(text, 5)
    assert sel is not None
    assert not sel.declined
    assert sel.index == expected_index
    assert sel.pack_count == pack


def test_decline() -> None:
    sel = parse_listed_option_reply("nai lagibo", 3)
    assert sel is not None and sel.declined


def test_unknown_short_text_returns_none() -> None:
    assert parse_listed_option_reply("hm", 3) is None
