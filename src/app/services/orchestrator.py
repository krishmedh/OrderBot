from __future__ import annotations

import logging
import re
from collections import defaultdict

from app.config import settings
from app.domain.intent_classification import IntentClassification
from app.domain.models import OrderItem, Product
from app.services.audio_service import AudioService
from app.services.conversation_memory import ConversationStore
from app.services.inventory_service import InventoryService, extract_product_keywords
from app.services.menu_commands import is_menu_command, looks_like_menu_request, menu_page_index
from app.services.shopping_intent_signals import (
    extracted_keywords_are_only_generic_fillers,
    looks_like_open_ended_shopping_without_product,
)
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.promo_service import PromotionService
from app.services.qa_service import QAService
from app.services.cart_commands import (
    find_cart_line_index,
    is_cart_management_command,
    pack_count_override_from_update_value,
    parse_remove_target,
    parse_update_command,
    wants_clear_cart,
    wants_show_cart,
)
from app.services.catalog_vector_store import search_catalog_context
from app.domain.intent_classification import ItemIntent
from app.services.cart_pricing import compute_cart_line
from app.services.multi_item_cart import (
    CartItemRequest,
    PendingQuantityBatch,
    build_cart_requests_from_entities,
    clause_to_cart_request,
    customer_quantity_specified,
    implies_single_catalog_pack,
    intent_quantity_is_variant_only,
    quantity_selects_product_variant,
    reply_matches_catalog_pack_size,
)
from app.services.cart_pricing import parse_weight_grams
from app.services.checkout_flow import (
    parse_checkout_payment_method,
    parse_delivery_details,
)
from app.services.shopping_session import (
    CartLine,
    PendingCheckout,
    PendingSingle,
    ShoppingSession,
    ShoppingSessionStore,
    cart_line_amount,
    cart_total_inr,
    filter_oil_products,
    is_negative_reply,
    parse_quantity_from_text,
    parse_shopping_confirmation,
    pick_product_from_message,
    user_asked_about_oil,
    wants_cart_checkout,
)
from app.services import reply_templates
from app.services.intent_classifier import IntentClassifierService
from app.services.intent_handlers import dispatch_intent
from app.services.intent_handlers.base import IntentHandlingContext
from app.services.option_selection import parse_listed_option_reply
from app.services.product_media import product_image_attachments


def _merged_order_items_from_cart(cart: list[CartLine]) -> list[OrderItem]:
    q: dict[str, int] = defaultdict(int)
    for line in cart:
        q[line.sku] += line.quantity
    return [OrderItem(sku=sku, quantity=qty) for sku, qty in sorted(q.items())]


def _user_utterance_for_memory(payload: dict, *, transcribed: str | None = None) -> str:
    if transcribed and transcribed.strip():
        return transcribed.strip()
    for key in ("customer_text", "message", "query"):
        v = (payload.get(key) or "").strip()
        if v:
            return v
    if payload.get("intent") == "place_order":
        items = payload.get("items") or []
        if items:
            return "order " + " ".join(f'{i["sku"]} x{i["quantity"]}' for i in items)
    if payload.get("intent") == "pay" and (oid := (payload.get("order_id") or "").strip()):
        return f"pay {oid}"
    if payload.get("intent") == "cancel_order" and (oid := (payload.get("order_id") or "").strip()):
        return f"cancel {oid}"
    if payload.get("intent") == "availability" and (sku := (payload.get("sku") or "").strip()):
        return f"availability {sku}"
    return ""


class CommerceOrchestrator:
    def __init__(
        self,
        inventory_service: InventoryService,
        order_service: OrderService,
        payment_service: PaymentService,
        qa_service: QAService,
        audio_service: AudioService,
        promotion_service: PromotionService,
        conversation_store: ConversationStore | None = None,
        shopping_sessions: ShoppingSessionStore | None = None,
        intent_classifier: IntentClassifierService | None = None,
    ) -> None:
        self.inventory_service = inventory_service
        self.order_service = order_service
        self.payment_service = payment_service
        self.qa_service = qa_service
        self.audio_service = audio_service
        self.promotion_service = promotion_service
        self._conversation = conversation_store or ConversationStore(settings.conversation_max_turns)
        self._shopping = shopping_sessions or ShoppingSessionStore()
        self._intent_classifier = intent_classifier or IntentClassifierService()

    def _use_intelligent_routing(self, payload: dict) -> bool:
        if settings.intent_legacy_flow:
            return False
        if payload.get("skip_intent_classification"):
            return False
        return True

    def shopping_turn(self, phone: str, store_id: str, user_text: str) -> dict | None:
        h = self._conversation.history(phone, store_id)
        return self._try_shopping_dialog(phone, store_id, user_text, h)

    def try_process_cart_requests(
        self,
        phone: str,
        store_id: str,
        requests: list[CartItemRequest],
    ) -> dict | None:
        """Bulk add (2+ lines) or ask quantity when a line has no amount; single line with qty uses yes/no flow."""
        if not requests:
            return None
        if len(requests) == 1:
            if customer_quantity_specified(requests[0]):
                return None
            sess = self._shopping.session(phone, store_id)
            return self._process_cart_requests(store_id, sess, requests)
        return self.add_cart_lines(phone, store_id, requests)

    def add_cart_lines(
        self,
        phone: str,
        store_id: str,
        requests: list[CartItemRequest],
    ) -> dict | None:
        """Add one or more lines immediately (used after intent classification)."""
        if not requests:
            return None
        sess = self._shopping.session(phone, store_id)
        return self._process_cart_requests(store_id, sess, requests)

    def try_add_multiple_cart_items(
        self,
        phone: str,
        store_id: str,
        requests: list[CartItemRequest],
    ) -> dict | None:
        """Add several catalogue lines in one turn (comma-separated or parallel entities)."""
        if len(requests) < 2:
            return None
        return self.try_process_cart_requests(phone, store_id, requests)

    def _refine_after_classification(
        self, classification: IntentClassification, user_text: str, store_id: str
    ) -> IntentClassification:
        """LLM output cleanup: confirmations, menu vs product, open-ended help."""
        text = (user_text or "").strip()

        if parse_shopping_confirmation(text)[0] or re.match(r"^\s*\d{1,2}\s*[.!?]?$", text):
            return classification.model_copy(
                update={
                    "items": {
                        "_confirm": ItemIntent(
                            intent="grocery",
                            sub_intent="add_to_cart",
                            normalized_query=text,
                        )
                    },
                    "confidence": max(classification.confidence, 0.95),
                }
            )

        if looks_like_menu_request(text):
            return classification.model_copy(
                update={
                    "items": {
                        "menu": ItemIntent(
                            intent="grocery",
                            sub_intent="query_items",
                            normalized_query="Show catalogue menu",
                        )
                    },
                    "confidence": max(classification.confidence, 0.95),
                }
            )

        upd = parse_update_command(text)
        if upd:
            item_q, new_val = upd
            return classification.model_copy(
                update={
                    "items": {
                        item_q.lower(): ItemIntent(
                            intent="grocery",
                            sub_intent="modify_item_from_cart",
                            quantity=new_val,
                            normalized_query=f"Update {item_q} to {new_val}",
                        )
                    },
                    "confidence": max(classification.confidence, 0.9),
                }
            )

        refined: dict[str, ItemIntent] = {}
        for key, item in classification.items.items():
            if item.sub_intent == "add_to_cart" and (
                looks_like_menu_request(key) or looks_like_menu_request(text)
            ):
                refined["menu"] = item.model_copy(
                    update={
                        "sub_intent": "query_items",
                        "normalized_query": "Show catalogue menu",
                    }
                )
                continue
            if item.sub_intent == "add_to_cart":
                blob = f"{text} {item.normalized_query}".strip()
                if looks_like_open_ended_shopping_without_product(blob):
                    refined["help"] = item.model_copy(
                        update={"sub_intent": "general_enquiry", "normalized_query": text}
                    )
                    continue
            refined[key] = item

        if not refined:
            refined = dict(classification.items)
        return classification.model_copy(update={"items": refined})

    def _remember_turn(self, phone: str, store_id: str, user_line: str, result: dict) -> dict:
        reply = (result.get("reply") or "").strip()
        user = (user_line or "").strip()
        if user and reply:
            self._conversation.append(phone, store_id, user, reply)
        return result

    def _products_map(self, store_id: str) -> dict:
        return {p.sku: p for p in self.inventory_service.list_all_products(store_id)}

    def _menu_page_products(self, store_id: str, page: int) -> list:
        products = self.inventory_service.list_all_products(store_id)
        start = page * reply_templates._MENU_PAGE_SIZE
        return products[start : start + reply_templates._MENU_PAGE_SIZE]

    def _cart_products(self, store_id: str, cart: list[CartLine]) -> list:
        by_sku = self._products_map(store_id)
        return [by_sku[line.sku] for line in cart if line.sku in by_sku]

    def _with_images(self, result: dict, products: list, *, max_count: int = 6) -> dict:
        if not products:
            return result
        images = product_image_attachments(
            products, max_count=max_count, currency=settings.default_currency
        )
        if images:
            return {**result, "images": images}
        return result

    def _resolve_product_for_phrase(
        self, store_id: str, phrase: str
    ) -> tuple[Product | None, list[Product]]:
        matches = self.inventory_service.catalog_matches(store_id, phrase)
        if user_asked_about_oil(phrase):
            oils = filter_oil_products(matches)
            if oils:
                matches = oils
        if not matches:
            return None, []
        if len(matches) == 1:
            return matches[0], []
        picked = pick_product_from_message(phrase, matches)
        if picked:
            return picked, []
        return None, matches

    def _resolve_product_for_cart_request(
        self, store_id: str, req: CartItemRequest
    ) -> tuple[Product | None, list[Product]]:
        phrase = (req.search_phrase or req.item or "").strip()
        product, amb = self._resolve_product_for_phrase(store_id, phrase)
        qty = (req.quantity or "").strip()
        if not qty or not re.fullmatch(r"\d+(?:\.\d+)?", qty):
            return product, amb
        item_key = req.item.strip()
        candidates = list(amb) if amb else ([product] if product else [])
        if product and not quantity_selects_product_variant(qty, product.name, product.sku):
            broader = self.inventory_service.catalog_matches(store_id, item_key)
            for p in broader:
                if p.sku not in {c.sku for c in candidates}:
                    candidates.append(p)
        for p in candidates:
            if quantity_selects_product_variant(qty, p.name, p.sku):
                return p, []
        picked = pick_product_from_message(f"{item_key} {qty}", candidates)
        if picked:
            return picked, []
        return product, amb

    def _append_product_line(
        self,
        store_id: str,
        sess,
        product: Product,
        user_text: str,
        *,
        pack_count_override: int | None = None,
    ) -> str | None:
        """Append one line to ``sess.cart``; return an error message or ``None`` on success."""
        packs, line_total, note = compute_cart_line(
            product, user_text, pack_count_override=pack_count_override
        )
        if product.quantity_available < packs:
            return (
                f"Sorry, we only have {product.quantity_available} pack(s) of {product.name} in stock "
                f"(you need {packs}). Try a lower amount or another item."
            )
        sess.cart.append(
            CartLine(
                sku=product.sku,
                quantity=packs,
                name=product.name,
                unit_price=product.price,
                line_total=line_total,
                weight_note=note,
            )
        )
        return None

    def _looks_like_quantity_reply(self, text: str, product: Product | None = None) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if re.fullmatch(r"\d{1,3}", t):
            return True
        if product and reply_matches_catalog_pack_size(t, product.name, product.sku):
            return True
        if customer_quantity_specified(clause_to_cart_request(t)):
            return True
        if parse_weight_grams(t) is not None:
            return True
        return parse_quantity_from_text(t, 0) > 0

    def _fulfill_pending_quantity(self, store_id: str, sess, trimmed: str) -> dict | None:
        batch: PendingQuantityBatch | None = sess.pending_quantity_batch
        if not batch:
            return None

        cur = settings.default_currency

        if is_negative_reply(trimmed):
            remaining = list(batch.remaining)
            sess.pending_quantity_batch = None
            if remaining:
                return self._process_cart_requests(
                    store_id, sess, remaining, added_so_far=list(batch.added_so_far)
                )
            return {
                "reply": (
                    "Okay, I have skipped that item. "
                    "Tell me what else you would like, or say **cart** to review."
                )
            }

        product = self.inventory_service.get_product(store_id, batch.sku)
        if not product:
            sess.pending_quantity_batch = None
            return {"reply": "That product is no longer in our catalogue."}

        if not self._looks_like_quantity_reply(trimmed, product):
            return {
                "reply": reply_templates.ask_quantity_for_product(
                    batch.item_label,
                    catalog_name=batch.product_name,
                    partial_lines=batch.added_so_far or None,
                    currency=cur,
                )
            }

        if reply_matches_catalog_pack_size(trimmed, product.name, product.sku):
            phrase = product.name
        else:
            phrase = f"{trimmed} {batch.item_label}".strip()
        err = self._append_product_line(store_id, sess, product, phrase)
        if err:
            return {"reply": err}

        line = sess.cart[-1]
        added = list(batch.added_so_far)
        added.append((line.name, cart_line_amount(line), line.weight_note))
        remaining = list(batch.remaining)
        sess.pending_quantity_batch = None
        sess.pending_single = None
        sess.pending_options = None

        if remaining:
            return self._process_cart_requests(store_id, sess, remaining, added_so_far=added)

        tot = cart_total_inr(sess.cart)
        if len(added) == 1:
            return self._with_images(
                {
                    "reply": reply_templates.cart_line_added(
                        line.name,
                        line.quantity,
                        cart_line_amount(line),
                        tot,
                        cur,
                        weight_note=line.weight_note,
                    )
                },
                [product],
                max_count=1,
            )
        return self._with_images(
            {
                "reply": reply_templates.cart_multiple_lines_added(
                    added, tot, cur
                )
            },
            [product],
            max_count=3,
        )

    def _process_cart_requests(
        self,
        store_id: str,
        sess,
        requests: list[CartItemRequest],
        *,
        added_so_far: list[tuple[str, float, str]] | None = None,
    ) -> dict | None:
        cur = settings.default_currency
        added: list[tuple[str, float, str]] = list(added_so_far or [])
        not_found: list[str] = []
        ambiguous: list[tuple[str, str]] = []
        stock_errors: list[str] = []
        image_products: list[Product] = []
        awaiting_quantity: list[tuple[CartItemRequest, Product]] = []

        for req in requests:
            phrase = (req.search_phrase or req.item or "").strip()
            if not phrase:
                continue

            product, amb = self._resolve_product_for_cart_request(store_id, req)
            if amb:
                opts = ", ".join(p.name for p in amb[:4])
                ambiguous.append((phrase, opts))
                continue
            if not product:
                not_found.append(req.item or phrase)
                continue

            item_label = req.item.strip() or phrase
            if not customer_quantity_specified(req) and not implies_single_catalog_pack(
                product.name, product.sku, item_label
            ):
                awaiting_quantity.append((req, product))
                continue

            if not customer_quantity_specified(req) and implies_single_catalog_pack(
                product.name, product.sku, item_label
            ):
                phrase = product.name

            pack_override: int | None = None
            if intent_quantity_is_variant_only(req, product.name, product.sku):
                phrase = product.name
                pack_override = 1

            err = self._append_product_line(
                store_id, sess, product, phrase, pack_count_override=pack_override
            )
            if err:
                stock_errors.append(err)
                continue
            line = sess.cart[-1]
            added.append((line.name, cart_line_amount(line), line.weight_note))
            image_products.append(product)

        if awaiting_quantity:
            first_req, first_product = awaiting_quantity[0]
            remaining = [r for r, _ in awaiting_quantity[1:]]
            sess.pending_quantity_batch = PendingQuantityBatch(
                sku=first_product.sku,
                product_name=first_product.name,
                item_label=first_req.item.strip() or first_product.name,
                remaining=remaining,
                added_so_far=list(added),
            )
            sess.pending_single = None
            sess.pending_options = None
            ask_product = first_product
            return self._with_images(
                {
                    "reply": reply_templates.ask_quantity_for_product(
                        sess.pending_quantity_batch.item_label,
                        catalog_name=first_product.name,
                        partial_lines=added or None,
                        currency=cur,
                    )
                },
                [ask_product],
                max_count=1,
            )

        if not added and not stock_errors:
            if ambiguous and not not_found:
                lines = "\n".join(f'• "{p}": {o}' for p, o in ambiguous)
                return {
                    "reply": (
                        "I found several products for some items. Please send one product at a time:\n\n"
                        f"{lines}"
                    )
                }
            if not_found:
                return {"reply": reply_templates.product_not_found(", ".join(not_found[:3]))}
            return None

        sess.pending_single = None
        sess.pending_options = None
        sess.pending_quantity_batch = None
        tot = cart_total_inr(sess.cart)
        if len(added) == 1 and not not_found and not ambiguous:
            name, line_total, note = added[0]
            line = sess.cart[-1]
            reply = reply_templates.cart_line_added(
                name,
                line.quantity,
                line_total,
                tot,
                cur,
                weight_note=note,
            )
        else:
            reply = reply_templates.cart_multiple_lines_added(
                added,
                tot,
                cur,
                not_found=not_found or None,
                ambiguous=ambiguous or None,
            )
        if stock_errors:
            reply += "\n\n" + "\n".join(stock_errors)
        return self._with_images({"reply": reply}, image_products, max_count=6)

    def _add_line_to_cart(
        self,
        store_id: str,
        sess,
        sku: str,
        user_text: str,
        *,
        pack_count_override: int | None = None,
    ) -> dict | None:
        p = self.inventory_service.get_product(store_id, sku)
        if not p:
            return {"reply": f"We could not find product {sku} in this store catalogue."}
        err = self._append_product_line(
            store_id, sess, p, user_text, pack_count_override=pack_count_override
        )
        if err:
            return {"reply": err}
        line = sess.cart[-1]
        line_total = cart_line_amount(line)
        tot = cart_total_inr(sess.cart)
        return self._with_images(
            {
                "reply": reply_templates.cart_line_added(
                    p.name,
                    line.quantity,
                    line_total,
                    tot,
                    settings.default_currency,
                    weight_note=line.weight_note,
                )
            },
            [p],
            max_count=1,
        )

    def _try_cart_management(self, store_id: str, sess, trimmed: str) -> dict | None:
        cur = settings.default_currency
        if wants_clear_cart(trimmed):
            sess.cart.clear()
            sess.pending_single = None
            sess.pending_options = None
            sess.pending_quantity_batch = None
            sess.pending_checkout = None
            return {"reply": reply_templates.cart_cleared()}

        if wants_show_cart(trimmed):
            return self._with_images(
                {"reply": reply_templates.cart_summary(sess.cart, cur)},
                self._cart_products(store_id, sess.cart),
                max_count=8,
            )

        remove_q = parse_remove_target(trimmed)
        if remove_q:
            if not sess.cart:
                return {"reply": reply_templates.checkout_cart_empty()}
            idx = find_cart_line_index(sess.cart, remove_q, self._products_map(store_id))
            if idx is None:
                return {"reply": f"I could not find \"{remove_q}\" in your cart. Say **cart** to see items."}
            removed = sess.cart.pop(idx)
            return {
                "reply": reply_templates.cart_item_removed(
                    removed.name, cart_total_inr(sess.cart), cur
                )
            }

        upd = parse_update_command(trimmed)
        if upd:
            if not sess.cart:
                return {"reply": reply_templates.checkout_cart_empty()}
            item_q, new_val = upd
            idx = find_cart_line_index(sess.cart, item_q, self._products_map(store_id))
            if idx is None:
                return {"reply": f"I could not find \"{item_q}\" in your cart. Say **cart** to see items."}
            line = sess.cart[idx]
            p = self.inventory_service.get_product(store_id, line.sku)
            if not p:
                sess.cart.pop(idx)
                return {"reply": "That item is no longer in the catalogue and was removed from your cart."}
            line_text = f"{item_q} {new_val}".strip()
            pack_override = pack_count_override_from_update_value(new_val)
            packs, line_total, note = compute_cart_line(
                p, line_text, pack_count_override=pack_override
            )
            if p.quantity_available < packs:
                return {
                    "reply": (
                        f"Sorry, only {p.quantity_available} pack(s) of {p.name} available; "
                        f"cannot set to {new_val}."
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
        return None

    def _try_shopping_dialog(
        self,
        phone: str,
        store_id: str,
        user_text: str,
        history: list[tuple[str, str]],
    ) -> dict | None:
        if not (phone or "").strip():
            return None

        sess = self._shopping.session(phone, store_id)
        cur = settings.default_currency
        trimmed = (user_text or "").strip()

        cart_mgmt = self._try_cart_management(store_id, sess, trimmed)
        if cart_mgmt is not None:
            return cart_mgmt

        if sess.pending_checkout:
            checkout_step = self._continue_checkout(phone, store_id, sess, trimmed)
            if checkout_step is not None:
                return checkout_step

        if sess.pending_quantity_batch:
            fulfilled = self._fulfill_pending_quantity(store_id, sess, trimmed)
            if fulfilled is not None:
                return fulfilled

        multi_reqs = build_cart_requests_from_entities(
            None, raw_text=trimmed, normalized_query=""
        )
        if len(multi_reqs) >= 2:
            bulk = self._process_cart_requests(store_id, sess, multi_reqs)
            if bulk is not None:
                return bulk

        if parse_shopping_confirmation(trimmed)[0] and not (
            sess.pending_single or sess.pending_options or sess.pending_checkout
        ):
            return {"reply": reply_templates.nothing_pending_for_yes()}

        if wants_cart_checkout(trimmed):
            if not sess.cart:
                return {"reply": reply_templates.checkout_cart_empty()}
            return self._begin_checkout(sess)

        if is_negative_reply(trimmed) and (
            sess.pending_single
            or sess.pending_options
            or sess.pending_quantity_batch
            or sess.pending_checkout
        ):
            if sess.pending_checkout:
                sess.pending_checkout = None
                return {
                    "reply": (
                        "Checkout cancelled. Your cart is unchanged — "
                        "say **checkout** when you are ready."
                    )
                }
            remaining = []
            if sess.pending_quantity_batch:
                remaining = list(sess.pending_quantity_batch.remaining)
            sess.pending_single = None
            sess.pending_options = None
            sess.pending_quantity_batch = None
            if remaining:
                return self._process_cart_requests(store_id, sess, remaining)
            return {
                "reply": (
                    "Understood, I have cancelled that selection. "
                    "Ask me about another product, or say **checkout** if your cart is ready."
                )
            }

        if sess.pending_options:
            n_opts = len(sess.pending_options)
            sel = parse_listed_option_reply(trimmed, n_opts)
            if sel and sel.declined:
                sess.pending_options = None
                return {
                    "reply": (
                        "Understood, I have cancelled that selection. "
                        "Ask me about another product, or say **checkout** if your cart is ready."
                    )
                }
            if sel and sel.index is not None:
                picked = sess.pending_options[sel.index]
                sess.pending_options = None
                line_text = trimmed
                if sel.pack_count:
                    line_text = f"{picked.name} {sel.pack_count}"
                return self._add_line_to_cart(
                    store_id,
                    sess,
                    picked.sku,
                    line_text,
                    pack_count_override=sel.pack_count,
                )
            picked = pick_product_from_message(trimmed, sess.pending_options)
            if picked:
                sess.pending_options = None
                return self._add_line_to_cart(store_id, sess, picked.sku, trimmed)
            if trimmed and len(trimmed) >= 2:
                return {
                    "reply": (
                        "I could not match that to one of the options I listed. "
                        "Please reply with **1**, **2**, a product name, or **cancel**."
                    )
                }
            return None

        if sess.pending_single:
            is_conf, qty_override = parse_shopping_confirmation(trimmed)
            if is_conf:
                pe = sess.pending_single
                sess.pending_single = None
                source = pe.source_text or trimmed
                if qty_override is not None:
                    return self._add_line_to_cart(
                        store_id,
                        sess,
                        pe.sku,
                        source,
                        pack_count_override=qty_override,
                    )
                return self._add_line_to_cart(store_id, sess, pe.sku, source)

        if sess.pending_single and trimmed and not parse_shopping_confirmation(trimmed)[0]:
            sess.pending_single = None

        if sess.pending_options and trimmed:
            if self.inventory_service.catalog_matches(store_id, trimmed):
                sess.pending_options = None

        matches = self.inventory_service.catalog_matches(store_id, trimmed)
        if not matches:
            if is_menu_command(trimmed):
                page = menu_page_index(trimmed)
                products = self.inventory_service.list_all_products(store_id)
                return self._with_images(
                    {
                        "reply": reply_templates.store_menu(
                            store_id.replace("_", " ").title(),
                            products,
                            settings.default_currency,
                            page,
                        )
                    },
                    self._menu_page_products(store_id, page),
                    max_count=6,
                )
            kws = extract_product_keywords(trimmed)
            if looks_like_open_ended_shopping_without_product(
                trimmed
            ) or extracted_keywords_are_only_generic_fillers(list(dict.fromkeys(kws))):
                return {"reply": reply_templates.shopping_help_clarify()}
            if kws:
                return {"reply": reply_templates.product_not_found(trimmed)}
            return None

        work = list(matches)
        if user_asked_about_oil(trimmed):
            oils = filter_oil_products(matches)
            if oils:
                work = oils

        if len(work) >= 2:
            sess.pending_options = list(work)
            sess.pending_single = None
            numbered = "\n".join(
                f"{i + 1}. {p.name} ({p.sku}) — {p.price:.2f} {cur}"
                for i, p in enumerate(work)
            )
            if user_asked_about_oil(trimmed) and filter_oil_products(matches):
                return self._with_images(
                    {"reply": reply_templates.oil_variant_prompt(numbered, cur)},
                    work[:4],
                    max_count=4,
                )
            return self._with_images(
                {"reply": reply_templates.multi_product_pick_prompt(numbered, cur)},
                work[:4],
                max_count=4,
            )

        one = work[0]
        qty = parse_quantity_from_text(trimmed, 1)
        packs, est_total, note = compute_cart_line(one, trimmed)
        sess.pending_single = PendingSingle(
            sku=one.sku,
            name=one.name,
            unit_price=one.price,
            quantity=qty,
            source_text=trimmed,
        )
        sess.pending_options = None
        detail_line = (
            f"- {one.name} ({one.sku}): {one.quantity_available} pack(s) in stock, "
            f"est. {est_total:.2f} {cur}"
        )
        if note:
            detail_line += f" — {note}"
        return self._with_images(
            {"reply": reply_templates.catalog_single_invite_yes(detail_line, one.sku, cur)},
            [one],
            max_count=1,
        )

    def _store_contact_display(self) -> str:
        return (settings.store_contact_phone or "").strip()

    def _begin_checkout(self, sess: ShoppingSession) -> dict:
        sess.pending_checkout = PendingCheckout(step="delivery")
        sess.pending_single = None
        sess.pending_options = None
        sess.pending_quantity_batch = None
        return {"reply": reply_templates.checkout_ask_delivery()}

    def _continue_checkout(
        self,
        phone: str,
        store_id: str,
        sess: ShoppingSession,
        trimmed: str,
    ) -> dict | None:
        pc = sess.pending_checkout
        if not pc:
            return None

        if is_negative_reply(trimmed):
            sess.pending_checkout = None
            return {
                "reply": (
                    "Checkout cancelled. Your cart is unchanged — "
                    "say **checkout** when you are ready."
                )
            }

        if pc.step == "delivery":
            parsed = parse_delivery_details(trimmed)
            if not parsed:
                return {"reply": reply_templates.checkout_ask_delivery_again()}
            addr, contact = parsed
            pc.delivery_address = addr
            pc.contact_phone = contact
            pc.step = "payment"
            return {"reply": reply_templates.checkout_ask_payment_method()}

        if pc.step == "payment":
            method = parse_checkout_payment_method(trimmed)
            if not method:
                return {"reply": reply_templates.checkout_ask_payment_method_again()}
            return self._finalize_checkout(phone, store_id, sess, method)

        return None

    def _finalize_checkout(
        self,
        phone: str,
        store_id: str,
        sess: ShoppingSession,
        payment_method: str,
    ) -> dict:
        pc = sess.pending_checkout
        if not pc or not sess.cart:
            sess.pending_checkout = None
            return {"reply": reply_templates.checkout_cart_empty()}

        items = _merged_order_items_from_cart(sess.cart)
        cur = settings.default_currency
        store_phone = self._store_contact_display()

        try:
            order = self.order_service.place_order(
                store_id,
                phone,
                items,
                delivery_address=pc.delivery_address,
                delivery_phone=pc.contact_phone,
                payment_method=payment_method,
            )
        except ValueError:
            return {"reply": reply_templates.checkout_system_error(store_phone)}
        except Exception:
            logging.getLogger(__name__).exception("checkout place_order failed")
            return {"reply": reply_templates.checkout_system_error(store_phone)}

        order_id = order.order_id
        total = order.total_amount
        sess.cart.clear()
        sess.pending_checkout = None
        sess.pending_single = None
        sess.pending_options = None
        sess.pending_quantity_batch = None

        if payment_method == "cod":
            return {
                "reply": reply_templates.checkout_cod_confirmed(order_id, total, cur),
                "order_id": order_id,
            }

        try:
            link = self.payment_service.initiate_payment(order_id)
        except Exception:
            logging.getLogger(__name__).exception("checkout payment link failed")
            return {
                "reply": reply_templates.checkout_payment_link_failed(order_id, store_phone),
                "order_id": order_id,
            }

        return {
            "reply": reply_templates.checkout_online_confirmed(order_id, total, cur, link),
            "order_id": order_id,
        }

    def handle(self, payload: dict) -> dict:
        intent = payload.get("intent", "question")
        phone = payload.get("phone") or ""
        store_id = payload.get("store_id") or settings.default_store_id
        history = self._conversation.history(phone, store_id)
        user_text = (
            payload.get("message")
            or payload.get("customer_text")
            or payload.get("query")
            or ""
        ).strip()

        menu_by_api_intent = intent == "menu"
        menu_text_shortcut = looks_like_menu_request(user_text)
        if menu_by_api_intent or menu_text_shortcut:
            u = _user_utterance_for_memory(payload) or user_text
            page = menu_page_index(u or user_text)
            products = self.inventory_service.list_all_products(store_id)
            reply = reply_templates.store_menu(
                store_id.replace("_", " ").title(),
                products,
                settings.default_currency,
                page,
            )
            return self._remember_turn(
                phone,
                store_id,
                u or "menu",
                self._with_images(
                    {"reply": reply},
                    self._menu_page_products(store_id, page),
                    max_count=6,
                ),
            )

        if intent == "greeting":
            u = _user_utterance_for_memory(payload)
            return self._remember_turn(
                phone,
                store_id,
                u or "hello",
                {"reply": reply_templates.greeting()},
            )

        if intent == "availability":
            sku = payload["sku"]
            text = self.inventory_service.check_availability(store_id, sku)
            u = _user_utterance_for_memory(payload)
            return self._remember_turn(
                phone,
                store_id,
                u or f"stock {sku}",
                {"reply": reply_templates.availability_detail(text)},
            )

        if intent == "place_order":
            items = [OrderItem(sku=i["sku"], quantity=i["quantity"]) for i in payload["items"]]
            order = self.order_service.place_order(store_id, phone, items)
            u = _user_utterance_for_memory(payload)
            return self._remember_turn(
                phone,
                store_id,
                u,
                {
                    "reply": reply_templates.order_confirmed(
                        order.order_id, order.total_amount, settings.default_currency
                    ),
                    "order_id": order.order_id,
                },
            )

        if intent == "pay":
            link = self.payment_service.initiate_payment(payload["order_id"])
            u = _user_utterance_for_memory(payload)
            return self._remember_turn(
                phone,
                store_id,
                u,
                {"reply": reply_templates.payment_link(link)},
            )

        if intent == "cancel_order":
            order = self.order_service.cancel_order(payload["order_id"])
            u = _user_utterance_for_memory(payload)
            return self._remember_turn(
                phone,
                store_id,
                u,
                {"reply": reply_templates.order_cancelled(order.order_id)},
            )

        if intent == "audio":
            transcribed = self.audio_service.transcribe_customer_audio(payload["audio_url"])
            answer = self.qa_service.answer_customer_question(transcribed, context="", history=history)
            return self._remember_turn(
                phone,
                store_id,
                transcribed,
                {"reply": answer, "transcribed_text": transcribed},
            )

        if intent == "broadcast":
            self.promotion_service.broadcast(payload["phones"], payload["message"])
            u = (payload.get("message") or "").strip()
            return self._remember_turn(
                phone,
                store_id,
                u,
                {"reply": reply_templates.broadcast_ack()},
            )

        if intent in ("question", "availability_search"):
            if intent == "availability_search":
                user_text = (
                    (payload.get("query") or payload.get("customer_text") or payload.get("message") or "")
                ).strip()
            else:
                user_text = (payload.get("message") or "").strip()
            mem_u = user_text or _user_utterance_for_memory(payload)

            if is_cart_management_command(mem_u):
                cart_r = self._try_shopping_dialog(phone, store_id, mem_u, history)
                if cart_r is not None:
                    return self._remember_turn(phone, store_id, mem_u, cart_r)

            sess = self._shopping.session(phone, store_id)
            if (
                sess.pending_options
                or sess.pending_quantity_batch
                or sess.pending_single
                or sess.pending_checkout
            ):
                pending_r = self._try_shopping_dialog(phone, store_id, mem_u, history)
                if pending_r is not None:
                    return self._remember_turn(phone, store_id, mem_u, pending_r)

            if self._use_intelligent_routing(payload):
                ic_log = {
                    "phone": phone,
                    "store_id": store_id,
                    "menu_context": search_catalog_context(
                        self.inventory_service, store_id, mem_u
                    ),
                }
                classification = self._intent_classifier.classify(
                    history, mem_u, log_context=ic_log
                )
                before_snap = list(classification.items.keys())
                classification = self._refine_after_classification(classification, mem_u, store_id)
                after_snap = list(classification.items.keys())
                if before_snap != after_snap:
                    logging.getLogger(__name__).info(
                        "[intent.refine] store=%s BEFORE=%s AFTER=%s raw_msg=%r",
                        store_id,
                        before_snap,
                        after_snap,
                        mem_u[:200],
                    )

                if not classification.items:
                    shop = self._try_shopping_dialog(phone, store_id, user_text, history)
                    if shop is not None:
                        merged = dict(shop)
                        merged["intent_analysis"] = classification.model_dump_json_safe()
                        return self._remember_turn(phone, store_id, mem_u, merged)

                hctx = IntentHandlingContext(
                    phone=phone,
                    store_id=store_id,
                    user_text=mem_u,
                    payload=payload,
                    history=history,
                    classification=classification,
                    orchestrator=self,
                )
                routed = dispatch_intent(hctx)
                if routed is not None:
                    reply = (routed.get("reply") or "").strip()
                    if reply or routed.get("images") or routed.get("order_id"):
                        merged = dict(routed)
                        merged["intent_analysis"] = classification.model_dump_json_safe()
                        orch_log = logging.getLogger("app.services.orchestrator")
                        orch_log.info(
                            "[intent-route] phone=%s store=%s items=%s conf=%.2f "
                            "merged_keys=%s reply_len=%s images=%s",
                            phone,
                            store_id,
                            list(classification.items.keys()),
                            classification.confidence,
                            sorted(merged.keys()),
                            len(reply),
                            len(merged.get("images") or []),
                        )
                        return self._remember_turn(phone, store_id, mem_u, merged)

            r = self._try_shopping_dialog(phone, store_id, user_text, history)
            if r is not None:
                return self._remember_turn(phone, store_id, mem_u, r)

        question = (payload.get("message") or "").strip()
        if intent == "availability_search":
            question = (payload.get("query") or question or "").strip()

        context = ""
        if sku := payload.get("sku"):
            context = self.inventory_service.check_availability(store_id, sku)
        reply = self.qa_service.answer_customer_question(question, context=context, history=history)
        return self._remember_turn(phone, store_id, question or _user_utterance_for_memory(payload), {"reply": reply})
