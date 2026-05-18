"""Per-primary-intent handler classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.intent_classification import IntentClassification

if TYPE_CHECKING:
    from app.services.orchestrator import CommerceOrchestrator


@dataclass
class IntentHandlingContext:
    phone: str
    store_id: str
    user_text: str
    payload: dict
    history: list[tuple[str, str]]
    classification: IntentClassification
    orchestrator: CommerceOrchestrator


class DomainIntentHandler(ABC):
    @abstractmethod
    def handle(self, ctx: IntentHandlingContext) -> dict | None:
        """Customer-facing reply dict (may include ``images``, ``intent_analysis``, etc.)."""
