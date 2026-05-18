from __future__ import annotations

from app.config import settings
from app.services import reply_templates
from app.services.cart_commands import (
    find_cart_line_index,
    pack_count_override_from_update_value,
)
from app.services.cart_pricing import compute_cart_line, parse_pack_length_meters
from app.services.intent_handlers.grocery_actions.base import GroceryActionHandler, ItemActionContext
from app.services.intent_prompt_context import looks_like_cart_increment
from app.services.shopping_session import cart_total_inr


class ModifyItemFromCartHandler(GroceryActionHandler):
    sub_intent = "modify_item_from_cart"

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

        line = sess.cart[idx]
        product = orch.inventory_service.get_product(ctx.store_id, line.sku)
        if not product:
            sess.cart.pop(idx)
            return {"reply": "That item is no longer in the catalogue and was removed from your cart."}

        new_val = (ctx.item.quantity or "").strip()
        if looks_like_cart_increment(ctx.user_text, ctx.item.normalized_query) or _is_increment_qty(
            new_val
        ):
            new_packs = line.quantity + 1
            pack_m = parse_pack_length_meters(product.name, product.sku)
            if pack_m and pack_m > 0:
                line_text = f"{ctx.item_key} {int(new_packs * pack_m)}m"
            else:
                line_text = f"{ctx.item_key} {new_packs}"
            packs, line_total, note = compute_cart_line(
                product, line_text, pack_count_override=new_packs
            )
        else:
            if not new_val:
                new_val = ctx.item.normalized_query or ctx.item_key
            line_text = f"{ctx.item_key} {new_val}".strip()
            pack_override = pack_count_override_from_update_value(new_val)
            packs, line_total, note = compute_cart_line(
                product, line_text, pack_count_override=pack_override
            )

        if product.quantity_available < packs:
            return {
                "reply": (
                    f"Sorry, only {product.quantity_available} pack(s) of {product.name} available."
                )
            }

        line.quantity = packs
        line.line_total = line_total
        line.weight_note = note
        return {
            "reply": reply_templates.cart_item_updated(
                line.name, line_total, cart_total_inr(sess.cart), cur, note
            )
        }


def _is_increment_qty(qty: str) -> bool:
    q = (qty or "").strip().lower()
    return q.startswith("+") or "one more" in q or q in {"+1", "+1 pack", "1 more"}
