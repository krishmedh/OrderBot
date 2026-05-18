from __future__ import annotations

from app.services.intent_handlers.grocery_actions.base import GroceryActionHandler, ItemActionContext


class DeleteCartHandler(GroceryActionHandler):
    sub_intent = "delete_cart"

    def handle(self, ctx: ItemActionContext) -> dict | None:
        return ctx.orchestrator.shopping_turn(ctx.phone, ctx.store_id, "clear cart")
