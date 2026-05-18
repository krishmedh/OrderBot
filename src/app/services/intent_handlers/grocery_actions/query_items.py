from __future__ import annotations

from app.config import settings
from app.services import reply_templates
from app.services.intent_handlers.grocery_actions.base import GroceryActionHandler, ItemActionContext
from app.services.menu_commands import looks_like_menu_request
from app.services.multi_item_cart import CartItemRequest, PendingQuantityBatch


class QueryItemsHandler(GroceryActionHandler):
    sub_intent = "query_items"

    def handle(self, ctx: ItemActionContext) -> dict | None:
        orch = ctx.orchestrator
        if ctx.item_key in ("menu", "catalogue", "catalog") or looks_like_menu_request(
            ctx.user_text
        ) or looks_like_menu_request(ctx.item.normalized_query):
            return orch.handle(
                {
                    "intent": "menu",
                    "message": ctx.user_text or "menu",
                    "phone": ctx.phone,
                    "store_id": ctx.store_id,
                }
            )

        store_id = ctx.store_id
        qty = (ctx.item.quantity or "").strip()
        product = None
        if qty:
            product, amb = orch._resolve_product_for_cart_request(
                store_id,
                CartItemRequest(
                    item=ctx.item_key,
                    quantity=qty,
                    search_phrase=f"{ctx.item_key} {qty}".strip(),
                ),
            )
            matches = [product] if product else list(amb)
        else:
            matches = orch.inventory_service.catalog_matches(store_id, ctx.item_key)
            if len(matches) == 1:
                product = matches[0]
            elif len(matches) > 1:
                product = None
            else:
                product, amb = orch._resolve_product_for_phrase(store_id, ctx.item_key)
                matches = list(amb) if amb else ([product] if product else [])

        if matches:
            return self._reply_availability(ctx, matches, product, variant_query=bool(qty))

        context = orch.inventory_service.check_availability(store_id, ctx.item_key)
        question = (ctx.item.normalized_query or ctx.user_text or ctx.item_key).strip()
        reply = orch.qa_service.answer_customer_question(
            question, context=context, history=ctx.history
        )
        return {"reply": reply}

    def _reply_availability(
        self, ctx: ItemActionContext, matches: list, product, *, variant_query: bool = False
    ) -> dict:
        orch = ctx.orchestrator
        sess = orch._shopping.session(ctx.phone, ctx.store_id)
        cur = settings.default_currency

        if variant_query and product:
            matches = [product]

        if len(matches) > 1 and not variant_query:
            in_stock = [p for p in matches if p.quantity_available > 0]
            if not in_stock:
                names = ", ".join(p.name for p in matches[:3])
                return {
                    "reply": f"Sorry, those items ({names}) are out of stock right now."
                }
            sess.pending_options = in_stock[:12]
            sess.pending_quantity_batch = None
            lines = [
                f"{i + 1}. {p.name} — {p.price:.2f} {cur} "
                f"({p.quantity_available} in stock)"
                for i, p in enumerate(in_stock[:12])
            ]
            return {
                "reply": (
                    "Yes, we have:\n"
                    + "\n".join(lines)
                    + "\n\nWhich one do you want? Reply **1**, **2**, or the pack size."
                )
            }

        p = product or matches[0]
        if p.quantity_available <= 0:
            return {"reply": f"Sorry, **{p.name}** is not in stock right now."}

        detail = (
            f"Yes — **{p.name}** is available: "
            f"{p.price:.2f} {cur}, {p.quantity_available} pack(s) in stock."
        )
        if variant_query:
            sess.pending_quantity_batch = None
            sess.pending_options = None
            return orch._with_images(
                {
                    "reply": (
                        detail
                        + "\n\nTo add this to your cart, reply **yes** or send how many packs you want."
                    )
                },
                [p],
                max_count=1,
            )

        sess.pending_quantity_batch = PendingQuantityBatch(
            sku=p.sku,
            product_name=p.name,
            item_label=ctx.item_key,
            remaining=[],
            added_so_far=[],
        )
        sess.pending_options = None
        reply = detail + "\n\n" + reply_templates.ask_quantity_for_product(
            ctx.item_key, catalog_name=p.name, currency=cur
        )
        return orch._with_images({"reply": reply}, [p], max_count=1)
