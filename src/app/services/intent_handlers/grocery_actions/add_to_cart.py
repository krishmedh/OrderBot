from __future__ import annotations

from app.domain.intent_classification import normalize_sub_intent
from app.services.intent_handlers.grocery_actions.base import GroceryActionHandler, ItemActionContext
from app.services.multi_item_cart import CartItemRequest


def cart_request_from_item(item_key: str, item) -> CartItemRequest:
    qty = (item.quantity or "").strip()
    phrase = item_key
    if qty:
        phrase = f"{phrase} {qty}".strip()
    return CartItemRequest(item=item_key, quantity=qty, search_phrase=phrase)


class AddToCartHandler(GroceryActionHandler):
    sub_intent = "add_to_cart"

    def handle(self, ctx: ItemActionContext) -> dict | None:
        orch = ctx.orchestrator
        if ctx.item_key.startswith("_"):
            return orch.shopping_turn(ctx.phone, ctx.store_id, ctx.user_text)
        req = cart_request_from_item(ctx.item_key, ctx.item)
        return orch.add_cart_lines(ctx.phone, ctx.store_id, [req])


def collect_add_to_cart_requests(classification) -> list[CartItemRequest]:
    """Build cart line requests for every add_to_cart item in one classification."""
    reqs: list[CartItemRequest] = []
    for key, item in classification.items.items():
        if key.startswith("_"):
            continue
        if normalize_sub_intent(item.sub_intent) != "add_to_cart":
            continue
        reqs.append(cart_request_from_item(key, item))
    return reqs
