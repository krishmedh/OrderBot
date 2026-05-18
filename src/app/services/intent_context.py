"""Build previous-message block for intent classification (growing conversation context)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def format_previous_message_block(
    history: list[tuple[str, str]],
    *,
    max_pairs: int | None = None,
    max_chars: int = 12000,
) -> str:
    """
    Turn transcript for the prompt's "Previous Message" section.
    Newest turns are at the end so the model sees full growing context.
    """
    if not history:
        return "(no prior turns in this conversation)"

    pairs = list(history)
    if max_pairs is not None:
        pairs = pairs[-max_pairs:]

    lines: list[str] = []
    for i, (user_msg, assistant_msg) in enumerate(pairs, start=1):
        u = (user_msg or "").strip()
        a = (assistant_msg or "").strip()
        if u:
            lines.append(f"[Turn {i}] User: {u}")
        if a:
            lines.append(f"[Turn {i}] Assistant: {a}")

    text = "\n".join(lines) if lines else "(no prior turns in this conversation)"
    over_chars = False
    if len(text) > max_chars:
        over_chars = True
        text = text[-max_chars:]
        text = "…(earlier context truncated)…\n" + text
    logger.info(
        "[intent.context] previous_message_block chars=%s turns_used=%s history_pairs=%s char_cap_hit=%s",
        len(text),
        len(pairs),
        len(history),
        over_chars,
    )
    return text
