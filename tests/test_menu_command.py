from app.services.menu_commands import is_menu_command, menu_page_index


def test_is_menu_command() -> None:
    assert is_menu_command("menu")
    assert is_menu_command("Menu")
    assert is_menu_command("menu 2")
    assert is_menu_command("menu please")
    assert is_menu_command("please menu")
    assert is_menu_command("show me the menu")
    assert is_menu_command("Please show me the menu")
    assert not is_menu_command("I want menu chicken")


def test_menu_page_index() -> None:
    assert menu_page_index("menu") == 0
    assert menu_page_index("menu 3") == 2
