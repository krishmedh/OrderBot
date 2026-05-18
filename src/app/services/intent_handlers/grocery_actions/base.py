"""Base class for a single grocery sub-intent action."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.intent_classification import ItemIntent

if TYPE_CHECKING:
    from app.services.orchestrator import CommerceOrchestrator


@dataclass
class ItemActionContext:
    phone: str
    store_id: str
    item_key: str
    item: ItemIntent
    user_text: str
    history: list[tuple[str, str]]
    orchestrator: CommerceOrchestrator


class GroceryActionHandler(ABC):
    sub_intent: str

    @abstractmethod
    def handle(self, ctx: ItemActionContext) -> dict | None:
        """Return partial result with optional ``reply``, ``images``, ``order_id``."""
