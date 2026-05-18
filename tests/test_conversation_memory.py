from app.services.conversation_memory import ConversationStore, conversation_memory_key


def test_memory_key_uses_digits_and_store() -> None:
    assert conversation_memory_key("+91 98765 43210", "store_north") == "store_north|919876543210"


def test_memory_truncates_old_pairs() -> None:
    store = ConversationStore(max_pairs=2)
    store.append("+1", "s", "u1", "a1")
    store.append("+1", "s", "u2", "a2")
    store.append("+1", "s", "u3", "a3")
    h = store.history("+1", "s")
    assert h == [("u2", "a2"), ("u3", "a3")]
