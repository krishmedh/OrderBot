"""Grocery domain: per-item sub-intent actions via GroceryActionExecutor."""

from __future__ import annotations

from app.services.intent_handlers.base import DomainIntentHandler, IntentHandlingContext
from app.services.intent_handlers.grocery_actions import GroceryActionExecutor


class GroceryPurchaseHandler(DomainIntentHandler):
    def __init__(self) -> None:
        self._executor = GroceryActionExecutor()

    def handle(self, ctx: IntentHandlingContext) -> dict | None:
        return self._executor.execute(ctx)
