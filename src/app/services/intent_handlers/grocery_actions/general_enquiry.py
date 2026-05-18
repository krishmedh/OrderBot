from __future__ import annotations

from app.services.intent_handlers.grocery_actions.base import GroceryActionHandler, ItemActionContext


class GeneralEnquiryHandler(GroceryActionHandler):
    sub_intent = "general_enquiry"

    def handle(self, ctx: ItemActionContext) -> dict | None:
        question = (
            (ctx.item.normalized_query or "").strip()
            or ctx.user_text.strip()
            or "How can I help you with your order?"
        )
        reply = ctx.orchestrator.qa_service.answer_customer_question(
            question, context="", history=ctx.history
        )
        return {"reply": reply}
