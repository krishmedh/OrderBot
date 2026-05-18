"""Polished customer-facing reply text for WhatsApp (plain text, concise)."""


def greeting() -> str:
    return (
        "Hello, and thank you for contacting us.\n\n"
        "We are here to help with product availability, placing an order, payment, or cancellations. "
        "Tell us what you need in a short message, or say what product you are looking for."
    )


def shopping_help_clarify() -> str:
    return (
        "Happy to help with groceries.\n\n"
        "What items do you need? Name products (for example rice, milk, detergent) or "
        "send **menu** to browse the full catalogue."
    )


def availability_detail(detail: str) -> str:
    return (
        "Thank you for checking with us.\n\n"
        f"{detail}\n\n"
        "If you would like to order this item, reply with: order <SKU> <quantity> (for example: order RICE-1KG 2)."
    )


def catalog_search_result(detail: str) -> str:
    return (
        "Thank you for your enquiry.\n\n"
        f"{detail}\n\n"
        "To order, reply with: order <SKU> <quantity>. For a specific SKU in stock, you can also say \"stock RICE-1KG\"."
    )


def catalog_single_invite_yes(detail_line: str, sku: str, currency: str) -> str:
    return (
        "Thank you for your enquiry.\n\n"
        f"{detail_line}\n\n"
        "If this is what you want, reply **yes** to add it to your cart.\n\n"
        f"SKU: {sku}  (or use: order {sku} 1)"
    )


def ask_quantity_for_product(
    item_label: str,
    *,
    catalog_name: str = "",
    partial_lines: list[tuple[str, float, str]] | None = None,
    currency: str = "INR",
) -> str:
    parts: list[str] = []
    if partial_lines:
        parts.append("Added to your cart so far:")
        for name, line_total, note in partial_lines:
            row = f"• {name}"
            if note:
                row += f" ({note})"
            row += f" — {line_total:.2f} {currency}"
            parts.append(row)
        parts.append("")
    label = (item_label or catalog_name or "this item").strip()
    parts.append(
        f"How much **{label}** do you need? "
        "Reply with a quantity (for example 250g, 1 bottle, 2 packs)."
    )
    if catalog_name and catalog_name.lower() != label.lower():
        parts.append(f"(In our catalogue: {catalog_name})")
    return "\n".join(parts)


def cart_multiple_lines_added(
    lines: list[tuple[str, float, str]],
    cart_total: float,
    currency: str,
    *,
    not_found: list[str] | None = None,
    ambiguous: list[tuple[str, str]] | None = None,
) -> str:
    """Summarize several cart lines just added (name, line_total, weight_note)."""
    parts: list[str] = ["Added to your cart:"]
    for name, line_total, note in lines:
        row = f"• {name}"
        if note:
            row += f" ({note})"
        row += f" — {line_total:.2f} {currency}"
        parts.append(row)

    parts.append(f"\nYour cart total is now: {cart_total:.2f} {currency}.")

    if not_found:
        parts.append("\nCould not find in our catalogue:")
        for q in not_found:
            parts.append(f"• {q}")

    if ambiguous:
        parts.append("\nPlease clarify which product you meant:")
        for phrase, options in ambiguous:
            parts.append(f"• \"{phrase}\": {options}")

    parts.append(
        "\nSay **cart** to review, **remove <item>** or **update <item> to 2 kg** to change lines, "
        "or **checkout** when ready."
    )
    return "\n".join(parts)


def cart_line_added(
    name: str,
    quantity: int,
    line_total: float,
    cart_total: float,
    currency: str,
    *,
    weight_note: str = "",
) -> str:
    detail = f"Added to your cart: {name}"
    if weight_note:
        detail += f" ({weight_note})"
    elif quantity > 1:
        detail += f" × {quantity} packs"
    return (
        f"{detail}.\n"
        f"Line total: {line_total:.2f} {currency}.\n"
        f"Your cart total is now: {cart_total:.2f} {currency}.\n\n"
        "Say **cart** to review, **remove <item>** or **update <item> to 2 kg** to change lines, "
        "or **checkout** when ready."
    )


def cart_summary(lines: list, currency: str) -> str:
    from app.services.shopping_session import cart_line_amount

    if not lines:
        return checkout_cart_empty()
    rows = []
    for i, line in enumerate(lines, start=1):
        amt = cart_line_amount(line)
        extra = f" — {line.weight_note}" if line.weight_note else ""
        rows.append(f"{i}. {line.name} ({line.sku}){extra}\n   {amt:.2f} {currency}")
    total = sum(cart_line_amount(line) for line in lines)
    body = "\n".join(rows)
    return (
        f"Your cart ({len(lines)} item(s)):\n\n{body}\n\n"
        f"Cart total: {total:.2f} {currency}\n\n"
        "Commands:\n"
        "• **remove <item>** — remove a line\n"
        "• **update <item> to 3** or **update moong dal to 5 kg** — change quantity/weight\n"
        "• **checkout** — place order"
    )


def cart_item_removed(name: str, cart_total: float, currency: str) -> str:
    return (
        f"Removed **{name}** from your cart.\n"
        f"Cart total is now: {cart_total:.2f} {currency}.\n\n"
        "Say **cart** to see remaining items."
    )


def cart_item_updated(name: str, line_total: float, cart_total: float, currency: str, note: str = "") -> str:
    extra = f" ({note})" if note else ""
    return (
        f"Updated **{name}**{extra}.\n"
        f"Line total: {line_total:.2f} {currency}.\n"
        f"Cart total is now: {cart_total:.2f} {currency}."
    )


def cart_cleared() -> str:
    return "Your cart is empty. Tell me what you would like to buy."


def oil_variant_prompt(numbered_lines: str, currency: str) -> str:
    return (
        "We have several cooking oils in 1 litre. Which one would you like?\n\n"
        f"{numbered_lines}\n\n"
        f"(Prices are in {currency}.)\n"
        "Reply with the name you prefer (for example: mustard, sunflower, refined)."
    )


def multi_product_pick_prompt(numbered_lines: str, currency: str) -> str:
    return (
        "Here are the closest matches in our catalogue:\n\n"
        f"{numbered_lines}\n\n"
        f"(Prices in {currency}.)\n"
        "Reply with the product name you want to look at first."
    )


def nothing_pending_for_yes() -> str:
    return (
        "I do not have an item waiting for confirmation right now. "
        "Ask me about a product (for example how much sugar you have), or say **checkout** if your cart is ready."
    )


def checkout_cart_empty() -> str:
    return "Your cart is empty. Tell me what you would like to buy, then say **checkout** when you are ready to pay."


def checkout_ask_delivery() -> str:
    return (
        "Great — let's finish your order.\n\n"
        "Please send your **delivery address** and **contact phone number** in one message.\n"
        "For example:\n"
        "House 12, ABC Colony, Guwahati\n"
        "9876543210"
    )


def checkout_ask_delivery_again() -> str:
    return (
        "I could not read a full address and phone number from that message.\n\n"
        "Please send your delivery address and a 10-digit mobile number "
        "(with or without +91), for example:\n"
        "House 12, ABC Colony, Guwahati\n"
        "9876543210"
    )


def checkout_ask_payment_method() -> str:
    return (
        "Thank you. How would you like to pay?\n\n"
        "Reply **COD** for cash on delivery\n"
        "Reply **Online** to pay now by UPI/card"
    )


def checkout_ask_payment_method_again() -> str:
    return "Please reply **COD** (cash on delivery) or **Online** (pay by UPI/card)."


def checkout_cod_confirmed(order_id: str, total: float, currency: str) -> str:
    return (
        "Your order is confirmed!\n\n"
        f"Order ID: {order_id}\n"
        f"Total: {total:.2f} {currency} (pay cash on delivery)\n\n"
        "We will deliver to you shortly. Our delivery partner will bring change "
        "and a QR code as well — in case you change your mind and prefer to pay online.\n\n"
        "Thank you for shopping with us."
    )


def checkout_online_confirmed(order_id: str, total: float, currency: str, payment_link: str) -> str:
    return (
        "Your order is recorded.\n\n"
        f"Order ID: {order_id}\n"
        f"Total: {total:.2f} {currency}\n\n"
        "Please complete your secure payment using the link below:\n"
        f"{payment_link}\n\n"
        "After payment, you will receive confirmation here."
    )


def checkout_system_error(store_phone: str) -> str:
    base = (
        "Sorry — something went wrong while placing your order. "
        "Your cart is still saved; you can try **checkout** again in a moment."
    )
    phone = (store_phone or "").strip()
    if phone:
        return f"{base}\n\nPlease call us at **{phone}** and we will take your order manually."
    return f"{base}\n\nPlease contact the store directly and we will take your order manually."


def checkout_payment_link_failed(order_id: str, store_phone: str) -> str:
    phone = (store_phone or "").strip()
    contact = (
        f"Please call us at **{phone}** to complete payment."
        if phone
        else "Please contact the store to complete payment."
    )
    return (
        f"Your order was recorded (Order ID: {order_id}), but we could not create a payment link.\n\n"
        f"{contact}"
    )


def product_not_found(query: str) -> str:
    q = (query or "").strip()
    return (
        f"Sorry, we do not have that item in our catalogue right now"
        + (f' ("{q}")' if q else "")
        + ".\n\n"
        "Send **menu** to see what we stock, or try another product name."
    )


def order_confirmed(order_id: str, total: float, currency: str) -> str:
    return (
        "Your order has been recorded successfully.\n\n"
        f"Order ID: {order_id}\n"
        f"Total: {total:.2f} {currency}\n\n"
        "To pay now, reply with:\n"
        f"pay {order_id}\n\n"
        "If you need to cancel before payment, reply with:\n"
        f"cancel {order_id}"
    )


def payment_link(link: str) -> str:
    return (
        "Thank you. Please complete your secure payment using the link below.\n\n"
        f"{link}\n\n"
        "After payment, you will receive confirmation here. If the link does not open, copy it into your browser."
    )


def order_cancelled(order_id: str) -> str:
    return (
        "Your cancellation request has been processed.\n\n"
        f"Order ID: {order_id}\n"
        "Status: cancelled.\n\n"
        "If you placed this order by mistake or need a new order, send us a message and we will assist you."
    )


_MENU_PAGE_SIZE = 20   # max products per WhatsApp message


def store_menu(store_name: str, products: list, currency: str, page: int = 0) -> str:
    """Format a page of products as a numbered menu.

    WhatsApp messages are capped at ~4096 chars, so we paginate at _MENU_PAGE_SIZE items.
    page=0 → first chunk, page=1 → second, etc.
    """
    from app.domain.models import Product  # avoid circular at module level

    start = page * _MENU_PAGE_SIZE
    chunk: list[Product] = products[start : start + _MENU_PAGE_SIZE]
    total = len(products)
    total_pages = max(1, -(-total // _MENU_PAGE_SIZE))  # ceil

    if not chunk:
        return f"{store_name} has no items in the catalogue right now."

    # Group by rough category based on SKU prefix
    lines: list[str] = []
    for i, p in enumerate(chunk, start=start + 1):
        lines.append(f"{i}. {p.name} — {p.price:.2f} {currency}")

    header = f"*{store_name} Menu*"
    if total_pages > 1:
        header += f" (page {page + 1} of {total_pages})"

    footer = "\nTell me the product you want, or ask about price/availability."
    if page + 1 < total_pages:
        footer += f"\nSend *menu {page + 2}* to see more."

    return header + "\n\n" + "\n".join(lines) + "\n" + footer


def broadcast_ack() -> str:
    return (
        "Your promotional broadcast has been queued for delivery to the selected customers.\n\n"
        "Thank you for using the store messaging tools."
    )
