from __future__ import annotations

from app.config import settings
from app.services import reply_templates
from app.services.cart_commands import find_cart_line_index
from app.services.intent_handlers.grocery_actions.base import GroceryActionHandler, ItemActionContext
from app.services.shopping_session import cart_total_inr


class RemoveFromCartHandler(GroceryActionHandler):
    sub_intent = "remove_from_cart"

    def handle(self, ctx: ItemActionContext) -> dict | None:
        orch = ctx.orchestrator
        sess = orch._shopping.session(ctx.phone, ctx.store_id)
        cur = settings.default_currency
        if not sess.cart:
            return {"reply": reply_templates.checkout_cart_empty()}
        idx = find_cart_line_index(
            sess.cart, ctx.item_key, orch._products_map(ctx.store_id)
        )
        if idx is None:
            return {
                "reply": (
                    f'I could not find "{ctx.item_key}" in your cart. Say **cart** to see items.'
                )
            }
        removed = sess.cart.pop(idx)
        return {
            "reply": reply_templates.cart_item_removed(
                removed.name, cart_total_inr(sess.cart), cur
            )
        }
