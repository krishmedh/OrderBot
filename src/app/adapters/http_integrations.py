import base64
import logging
import time
from typing import Iterable

import httpx

from app.config import settings
from app.domain.interfaces import PaymentGateway, QAProvider, SpeechToTextProvider, WhatsAppGateway
from app.logging_setup import format_json_for_log, truncate_for_log

logger = logging.getLogger(__name__)
_openai_dump = logging.getLogger("app.openai.qa")

WHATSAPP_QA_SYSTEM_PROMPT = (
    "You are a professional customer-care assistant for a retail store on WhatsApp. "
    "Reply in clear, polite, concise plain text (no markdown). "
    "Match the customer's language when possible (English, Hindi, Bengali, Assamese). "
    "Use the catalogue context when provided; if information is missing, say so honestly and suggest next steps. "
    "Do not invent prices or stock; only use facts from the context for inventory. "
    "You may use earlier messages in this chat when the customer refers back or asks a short follow-up "
    "(for example prices, quantities, or 'the same item'). "
    "Keep replies under about 1200 characters when possible."
)


def _whatsapp_qa_user_turn_text(question: str, context: str) -> str:
    return question if not context else f"Store catalogue context:\n{context}\n\nCustomer question:\n{question}"


def build_whatsapp_qa_messages(
    question: str,
    context: str,
    history: list[tuple[str, str]] | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": WHATSAPP_QA_SYSTEM_PROMPT}]
    for user_msg, assistant_msg in history or []:
        u = (user_msg or "").strip()
        a = (assistant_msg or "").strip()
        if u:
            messages.append({"role": "user", "content": u})
        if a:
            messages.append({"role": "assistant", "content": a})
    messages.append({"role": "user", "content": _whatsapp_qa_user_turn_text(question, context)})
    return messages


def _openai_qa_fallback(question: str, context: str) -> str:
    q = (question or "").strip()
    if context:
        return (
            "We are temporarily unable to reach our assistant service due to high demand or a service limit. "
            "Here is what we can share from our catalogue right now:\n\n"
            f"{context}\n\n"
            "Please try your question again in a minute, or tell us the product SKU so we can help with stock and orders."
        )
    return (
        "Thank you for your message. Our assistant is briefly unavailable (rate limit). "
        "Please try again in a minute.\n\n"
        f'When you retry, you can repeat your question; it was: "{q}"' if q else "Please try again in a minute."
    )


class WhatsAppCloudGateway(WhatsAppGateway):
    def __init__(self, access_token: str, phone_number_id: str, api_version: str = "v19.0") -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version

    def _messages_url(self, phone_number_id: str | None = None) -> str:
        pnid = (phone_number_id or self.phone_number_id or "").strip()
        return f"https://graph.facebook.com/{self.api_version}/{pnid}/messages"

    @staticmethod
    def _recipient_digits(phone: str) -> str:
        digits = "".join(c for c in phone if c.isdigit())
        return digits if digits else phone

    def _send_text(
        self,
        phone: str,
        text: str,
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        to_id = self._recipient_digits(phone)
        pnid = (from_phone_number_id or self.phone_number_id or "").strip()
        payload = {
            "messaging_product": "whatsapp",
            "to": to_id,
            "type": "text",
            "text": {"body": text},
        }
        url = self._messages_url(pnid)
        response = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        if response.is_error:
            logger.error(
                "WhatsApp Graph API send failed status=%s phone_number_id=%s to=%s body=%s",
                response.status_code,
                pnid,
                to_id,
                response.text[:2000],
            )
        response.raise_for_status()

    def send_message(
        self,
        phone: str,
        text: str,
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        self._send_text(phone, text, from_phone_number_id=from_phone_number_id)

    def send_image(
        self,
        phone: str,
        image_url: str,
        caption: str = "",
        *,
        from_phone_number_id: str | None = None,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        to_id = self._recipient_digits(phone)
        pnid = (from_phone_number_id or self.phone_number_id or "").strip()
        payload: dict = {
            "messaging_product": "whatsapp",
            "to": to_id,
            "type": "image",
            "image": {"link": image_url},
        }
        cap = (caption or "").strip()
        if cap:
            payload["image"]["caption"] = cap[:1024]
        response = httpx.post(
            self._messages_url(pnid), headers=headers, json=payload, timeout=20.0
        )
        response.raise_for_status()

    def send_broadcast(self, phones: Iterable[str], text: str) -> None:
        for phone in phones:
            self._send_text(phone, text)


class StripePaymentGateway(PaymentGateway):
    def __init__(self, secret_key: str) -> None:
        self.secret_key = secret_key
        self.base_url = "https://api.stripe.com/v1/payment_links"

    def create_payment_link(self, order_id: str, amount: float) -> str:
        # Stripe expects amount in the smallest unit, e.g. paise/cents.
        unit_amount = int(amount * 100)
        auth = base64.b64encode(f"{self.secret_key}:".encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "line_items[0][price_data][currency]": settings.default_currency.lower(),
            "line_items[0][price_data][product_data][name]": f"Order {order_id}",
            "line_items[0][price_data][unit_amount]": str(unit_amount),
            "line_items[0][quantity]": "1",
            "metadata[order_id]": order_id,
        }
        response = httpx.post(self.base_url, headers=headers, data=data, timeout=20.0)
        response.raise_for_status()
        body = response.json()
        return body.get("url", "")


class RazorpayPaymentGateway(PaymentGateway):
    def __init__(self, key_id: str, key_secret: str) -> None:
        self.key_id = key_id
        self.key_secret = key_secret
        self.base_url = "https://api.razorpay.com/v1/payment_links"

    def create_payment_link(self, order_id: str, amount: float) -> str:
        payload = {
            "amount": int(amount * 100),
            "currency": settings.default_currency,
            "accept_partial": False,
            "description": f"Order {order_id}",
            "reference_id": order_id,
        }
        response = httpx.post(
            self.base_url,
            json=payload,
            auth=(self.key_id, self.key_secret),
            timeout=20.0,
        )
        response.raise_for_status()
        body = response.json()
        return body.get("short_url", "")


class OpenAIQAProvider(QAProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1/chat/completions"

    def try_chat(
        self,
        question: str,
        context: str = "",
        history: list[tuple[str, str]] | None = None,
    ) -> str | None:
        """Return assistant text on success; None if OpenAI cannot answer (for chaining to Ollama)."""
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": build_whatsapp_qa_messages(question, context, history),
            "temperature": 0.3,
        }
        if settings.log_openai_dump_full:
            _openai_dump.info("[openai.dump.qa] REQUEST\n%s", format_json_for_log(dict(payload)))

        max_attempts = 4
        for attempt in range(max_attempts):
            try:
                response = httpx.post(self.base_url, headers=headers, json=payload, timeout=45.0)
            except httpx.RequestError as exc:
                logger.warning("OpenAI chat request error: %s", exc)
                return None

            body_json: object | None = None
            try:
                body_json = response.json()
            except ValueError:
                body_json = None

            if settings.log_openai_dump_full:
                if isinstance(body_json, dict):
                    _openai_dump.info(
                        "[openai.dump.qa] RESPONSE attempt=%s status=%s\n%s",
                        attempt + 1,
                        response.status_code,
                        format_json_for_log(body_json),
                    )
                elif body_json is not None:
                    _openai_dump.info(
                        "[openai.dump.qa] RESPONSE attempt=%s status=%s (non-object)\n%s",
                        attempt + 1,
                        response.status_code,
                        format_json_for_log({"json": body_json}),
                    )
                else:
                    _openai_dump.warning(
                        "[openai.dump.qa] RESPONSE(non_json) attempt=%s status=%s\n%s",
                        attempt + 1,
                        response.status_code,
                        truncate_for_log(response.text or ""),
                    )

            if response.status_code == 429:
                wait_s = min(60.0, 2.0 * (2**attempt))
                ra = response.headers.get("retry-after")
                if ra:
                    try:
                        wait_s = min(60.0, float(ra))
                    except ValueError:
                        pass
                logger.warning(
                    "OpenAI chat rate limited (429), attempt %s/%s, sleeping %.1fs",
                    attempt + 1,
                    max_attempts,
                    wait_s,
                )
                if attempt < max_attempts - 1:
                    time.sleep(wait_s)
                continue

            if response.is_success:
                try:
                    if isinstance(body_json, dict):
                        body = body_json
                    else:
                        body = response.json()
                    return body["choices"][0]["message"]["content"].strip()
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    logger.error("OpenAI chat unexpected JSON: %s", exc)
                    return None

            logger.error(
                "OpenAI chat HTTP %s: %s",
                response.status_code,
                (response.text or "")[:800],
            )
            return None

        return None

    def answer(
        self,
        question: str,
        context: str = "",
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        return self.try_chat(question, context, history) or _openai_qa_fallback(question, context)


class OllamaQAProvider(QAProvider):
    """Local LLM via Ollama HTTP API (`/api/chat`)."""

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._chat_url = f"{self.base_url}/api/chat"

    def answer(
        self,
        question: str,
        context: str = "",
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": build_whatsapp_qa_messages(question, context, history),
            "stream": False,
        }
        try:
            response = httpx.post(self._chat_url, json=payload, timeout=120.0)
        except httpx.RequestError as exc:
            logger.warning("Ollama chat request error: %s", exc)
            return _openai_qa_fallback(question, context)

        if not response.is_success:
            logger.error("Ollama chat HTTP %s: %s", response.status_code, (response.text or "")[:800])
            return _openai_qa_fallback(question, context)

        try:
            body = response.json()
            msg = body.get("message") or {}
            text = (msg.get("content") or "").strip()
            return text if text else _openai_qa_fallback(question, context)
        except (ValueError, TypeError) as exc:
            logger.error("Ollama chat unexpected JSON: %s", exc)
            return _openai_qa_fallback(question, context)


class OpenAISpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1/audio/transcriptions"

    def transcribe(self, audio_url: str) -> str:
        # In production, download media from WhatsApp and send binary file.
        # This scaffold posts a URL string as metadata placeholder.
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": ("audio-url.txt", audio_url.encode("utf-8"), "text/plain")}
        data = {"model": "gpt-4o-mini-transcribe"}
        response = httpx.post(self.base_url, headers=headers, files=files, data=data, timeout=30.0)
        response.raise_for_status()
        body = response.json()
        return body.get("text", "")
