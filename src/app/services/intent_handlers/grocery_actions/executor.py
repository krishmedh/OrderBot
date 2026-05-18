"""Run each classified item action and merge customer replies."""

from __future__ import annotations

import logging

from app.domain.intent_classification import IntentClassification, ItemIntent, normalize_sub_intent
from app.services.intent_handlers.base import IntentHandlingContext
from app.services.intent_handlers.grocery_actions.add_to_cart import (
    AddToCartHandler,
    collect_add_to_cart_requests,
)
from app.services.intent_handlers.grocery_actions.base import GroceryActionHandler, ItemActionContext
from app.services.intent_handlers.grocery_actions.checkout import CheckoutHandler
from app.services.intent_handlers.grocery_actions.delete_cart import DeleteCartHandler
from app.services.intent_handlers.grocery_actions.general_enquiry import GeneralEnquiryHandler
from app.services.intent_handlers.grocery_actions.modify_item_from_cart import (
    ModifyItemFromCartHandler,
)
from app.services.intent_handlers.grocery_actions.query_items import QueryItemsHandler
from app.services.intent_handlers.grocery_actions.remove_from_cart import RemoveFromCartHandler
from app.services.intent_handlers.grocery_actions.view_cart import ViewCartHandler

logger = logging.getLogger(__name__)

_HANDLERS: dict[str, GroceryActionHandler] = {
    "query_items": QueryItemsHandler(),
    "add_to_cart": AddToCartHandler(),
    "remove_from_cart": RemoveFromCartHandler(),
    "modify_item_from_cart": ModifyItemFromCartHandler(),
    "delete_cart": DeleteCartHandler(),
    "checkout": CheckoutHandler(),
    "general_enquiry": GeneralEnquiryHandler(),
    "view_cart": ViewCartHandler(),
}


def _handler_for(item: ItemIntent) -> GroceryActionHandler:
    sub = normalize_sub_intent(item.sub_intent)
    return _HANDLERS.get(sub) or AddToCartHandler()


class GroceryActionExecutor:
    def execute(self, ctx: IntentHandlingContext) -> dict | None:
        classification: IntentClassification = ctx.classification
        items = classification.grocery_items()
        if not items:
            return None

        replies: list[str] = []
        images: list = []
        order_id: str | None = None

        add_reqs = collect_add_to_cart_requests(classification)
        if add_reqs:
            logger.info(
                "[grocery.action] bulk_add count=%s keys=%s",
                len(add_reqs),
                [r.item for r in add_reqs],
            )
            bulk = ctx.orchestrator.add_cart_lines(ctx.phone, ctx.store_id, add_reqs)
            if bulk:
                r = (bulk.get("reply") or "").strip()
                if r:
                    replies.append(r)
                if bulk.get("images"):
                    images.extend(bulk["images"])

        for item_key, item in items:
            if normalize_sub_intent(item.sub_intent) == "add_to_cart":
                continue
            sub = normalize_sub_intent(item.sub_intent)
            logger.info(
                "[grocery.action] key=%r sub_intent=%s norm=%r",
                item_key,
                sub,
                (item.normalized_query or "")[:120],
            )
            handler = _handler_for(item)
            actx = ItemActionContext(
                phone=ctx.phone,
                store_id=ctx.store_id,
                item_key=item_key,
                item=item,
                user_text=ctx.user_text,
                history=ctx.history,
                orchestrator=ctx.orchestrator,
            )
            result = handler.handle(actx)
            if not result:
                continue
            r = (result.get("reply") or "").strip()
            if r:
                replies.append(r)
            if result.get("images"):
                images.extend(result["images"])
            if result.get("order_id"):
                order_id = result["order_id"]

        if not replies and not images and not order_id:
            return None

        out: dict = {"reply": "\n\n".join(replies) if replies else ""}
        if images:
            out["images"] = images[:8]
        if order_id:
            out["order_id"] = order_id
        return out
