"""IntentClassification → DomainIntentHandler."""

from __future__ import annotations

import logging

from app.services.intent_handlers.base import DomainIntentHandler, IntentHandlingContext
from app.services.intent_handlers.grocery import GroceryPurchaseHandler
from app.services.intent_handlers.stubs import (
    DoctorAppointmentHandler,
    HaircutBookingHandler,
    MedicinePurchaseHandler,
    PropertySearchHandler,
    TicketBookingHandler,
    UnknownIntentHandler,
)

logger = logging.getLogger(__name__)

_HANDLERS: dict[str, DomainIntentHandler] = {
    "GROCERY_PURCHASE": GroceryPurchaseHandler(),
    "HAIRCUT_BOOKING": HaircutBookingHandler(),
    "MEDICINE_PURCHASE": MedicinePurchaseHandler(),
    "DOCTOR_APPOINTMENT": DoctorAppointmentHandler(),
    "TICKET_BOOKING": TicketBookingHandler(),
    "PROPERTY_SEARCH": PropertySearchHandler(),
    "UNKNOWN": UnknownIntentHandler(),
}


def dispatch_intent(ctx: IntentHandlingContext) -> dict | None:
    key = ctx.classification.intent
    handler = _HANDLERS.get(key) or UnknownIntentHandler()
    logger.info(
        "[intent.dispatch] primary=%s items=%s handler_class=%s user_preview=%r",
        ctx.classification.intent,
        list(ctx.classification.items.keys()),
        type(handler).__name__,
        (ctx.user_text or "")[:180],
    )
    return handler.handle(ctx)
