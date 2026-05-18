"""Non-grocery domains: polite unavailability until separate services are wired."""

from __future__ import annotations

from app.services.intent_handlers.base import DomainIntentHandler, IntentHandlingContext


class HaircutBookingHandler(DomainIntentHandler):
    def handle(self, ctx: IntentHandlingContext) -> dict | None:
        return {
            "reply": (
                "This assistant is set up for grocery shopping right now. "
                "Salon or haircut booking is not connected on this number yet. "
                "If you meant groceries, say what you need (for example milk, rice, or oil)."
            )
        }


class MedicinePurchaseHandler(DomainIntentHandler):
    def handle(self, ctx: IntentHandlingContext) -> dict | None:
        return {
            "reply": (
                "Medicine orders are not enabled on this chat yet. "
                "This store currently handles grocery items only. "
                "Tell me a grocery product if you would like to shop."
            )
        }


class DoctorAppointmentHandler(DomainIntentHandler):
    def handle(self, ctx: IntentHandlingContext) -> dict | None:
        return {
            "reply": (
                "Doctor appointments are not booked through this grocery assistant. "
                "Please contact your clinic or hospital directly. "
                "I can still help with grocery shopping if you say what you need."
            )
        }


class TicketBookingHandler(DomainIntentHandler):
    def handle(self, ctx: IntentHandlingContext) -> dict | None:
        return {
            "reply": (
                "Ticket booking (travel/events) is not available here. "
                "This assistant is for your store’s groceries. "
                "Ask for a product name or send “menu” to see the catalogue."
            )
        }


class PropertySearchHandler(DomainIntentHandler):
    def handle(self, ctx: IntentHandlingContext) -> dict | None:
        return {
            "reply": (
                "Property search is not available on this grocer chat. "
                "You can browse food and household items—send “menu” or name what you need."
            )
        }


class UnknownIntentHandler(DomainIntentHandler):
    def handle(self, ctx: IntentHandlingContext) -> dict | None:
        orch = ctx.orchestrator
        question = (
            (ctx.classification.normalized_query or "").strip()
            or ctx.user_text.strip()
        )
        context = ""
        if sku := (ctx.payload.get("sku") or "").strip():
            context = orch.inventory_service.check_availability(ctx.store_id, sku)
        reply = orch.qa_service.answer_customer_question(
            question, context=context, history=ctx.history
        )
        return {"reply": reply}
