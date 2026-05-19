import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.adapters.meta_inbound import iter_meta_message_bundles, message_to_orchestrator_payload
from app.adapters.store_routing import resolve_store_id
from app.api.schemas import WhatsAppEvent
from app.api.security import is_valid_whatsapp_signature
from app.config import settings
from app.domain.interfaces import WhatsAppGateway
from app.services.orchestrator import CommerceOrchestrator

logger = logging.getLogger(__name__)


def _summarize_meta_message(msg: dict) -> str:
    mtype = msg.get("type", "?")
    mid = msg.get("id", "?")
    frm = msg.get("from", "?")
    if mtype == "text":
        body = (msg.get("text") or {}).get("body") or ""
        preview = body[:500] + ("…" if len(body) > 500 else "")
        return f"id={mid} from={frm} type=text body={preview!r}"
    if mtype == "audio":
        aid = (msg.get("audio") or {}).get("id", "")
        return f"id={mid} from={frm} type=audio media_id={aid!r}"
    return f"id={mid} from={frm} type={mtype}"


def _webhook_signature_secret() -> str:
    return settings.meta_app_secret or settings.webhook_verify_secret


def _handle_meta_whatsapp_message(
    orchestrator: CommerceOrchestrator,
    whatsapp_gateway: WhatsAppGateway,
    wa_from: str,
    msg: dict,
    phone_number_id: str,
    store_id: str,
) -> None:
    """Process one inbound WhatsApp message and send the reply via Graph API."""
    payload = message_to_orchestrator_payload(wa_from, msg, store_id)
    logger.info(
        "WhatsApp webhook mapped intent=%s phone=%s keys=%s",
        payload.get("intent"),
        payload.get("phone", wa_from),
        sorted(k for k in payload if k not in ("message",) and payload.get(k) is not None),
    )
    if payload.get("message"):
        mq = str(payload["message"])
        logger.info(
            "WhatsApp webhook customer text (truncated): %s",
            mq[:800] + ("…" if len(mq) > 800 else ""),
        )

    message_id = str(msg.get("id") or "").strip()
    send_kw = {"from_phone_number_id": phone_number_id} if phone_number_id else {}
    if message_id and settings.whatsapp_typing_indicator:
        try:
            whatsapp_gateway.mark_read_and_show_typing(message_id, **send_kw)
        except Exception:
            logger.exception(
                "WhatsApp typing indicator failed for message_id=%s to=%s",
                message_id,
                wa_from,
            )

    result = orchestrator.handle(payload)
    ia_meta = result.get("intent_analysis") or {}
    logger.info(
        "WhatsApp webhook classified intent=%s sub_intent=%s conf=%s reply_chars=%s",
        ia_meta.get("intent"),
        ia_meta.get("sub_intent"),
        ia_meta.get("confidence"),
        len(result.get("reply") or ""),
    )
    reply_text = result.get("reply")
    if reply_text:
        preview = reply_text[:400] + ("…" if len(reply_text) > 400 else "")
        logger.info("WhatsApp webhook outbound preview to=%s: %s", wa_from, preview)
        try:
            whatsapp_gateway.send_message(wa_from, reply_text[:4096], **send_kw)
        except Exception:
            logger.exception("WhatsApp send_message failed for to=%s", wa_from)
    for img in (result.get("images") or [])[:3]:
        try:
            whatsapp_gateway.send_image(
                wa_from,
                img["url"],
                img.get("caption") or "",
                **send_kw,
            )
        except Exception:
            logger.exception(
                "WhatsApp send_image failed for to=%s url=%s",
                wa_from,
                img.get("url"),
            )
    if not reply_text and not result.get("images"):
        logger.warning(
            "WhatsApp webhook no reply generated for from=%s intent=%s",
            wa_from,
            payload.get("intent"),
        )


def create_router(
    orchestrator: CommerceOrchestrator,
    whatsapp_gateway: WhatsAppGateway,
    store_routing: dict,
    default_store_id: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/webhook/whatsapp")
    def verify_whatsapp_webhook(request: Request) -> PlainTextResponse:
        """Meta WhatsApp Cloud API subscription verification (required once per callback URL)."""
        params = request.query_params
        hub_mode = params.get("hub.mode") or params.get("hub_mode")
        hub_verify_token = params.get("hub.verify_token") or params.get("hub_verify_token")
        hub_challenge = params.get("hub.challenge") or params.get("hub_challenge")
        expected = (settings.whatsapp_verify_token or "").strip()
        got = (hub_verify_token or "").strip()

        logger.info(
            "WhatsApp webhook verify attempt mode=%s token_match=%s challenge_len=%s client=%s",
            hub_mode,
            bool(expected and got and got == expected),
            len(hub_challenge or ""),
            (request.headers.get("user-agent") or "")[:80],
        )

        if hub_mode == "subscribe" and expected and got == expected:
            return PlainTextResponse(content=hub_challenge or "", status_code=200)

        logger.warning(
            "WhatsApp webhook verify failed mode=%r expected_token_set=%s token_len=%s",
            hub_mode,
            bool(expected),
            len(got),
        )
        raise HTTPException(status_code=403, detail="Verification failed.")

    @router.post("/webhook/whatsapp")
    async def receive_whatsapp_event(
        request: Request,
        background_tasks: BackgroundTasks,
        x_hub_signature_256: str | None = Header(default=None),
    ) -> dict:
        raw_body = await request.body()

        try:
            data = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc

        # Meta WhatsApp Cloud API sends this shape; replies must go out via Graph API (send_message).
        if data.get("object") == "whatsapp_business_account":
            if not is_valid_whatsapp_signature(_webhook_signature_secret(), raw_body, x_hub_signature_256):
                raise HTTPException(status_code=401, detail="Invalid webhook signature.")
            for value, msg in iter_meta_message_bundles(data):
                wa_from = msg.get("from") or ""
                if not wa_from:
                    continue
                metadata = value.get("metadata") or {}
                phone_number_id = str(metadata.get("phone_number_id") or "").strip()
                store_id = resolve_store_id(metadata, store_routing, default_store_id)
                logger.info(
                    "WhatsApp webhook inbound: %s phone_number_id=%s store_id=%s",
                    _summarize_meta_message(msg),
                    phone_number_id or "?",
                    store_id,
                )
                background_tasks.add_task(
                    _handle_meta_whatsapp_message,
                    orchestrator,
                    whatsapp_gateway,
                    wa_from,
                    msg,
                    phone_number_id,
                    store_id,
                )
            return {"status": "ok"}

        # Dev / direct JSON API (curl, Postman) — same path, simplified schema.
        event = WhatsAppEvent.model_validate(data)
        dumped = event.model_dump(exclude_none=True)
        dumped.setdefault("store_id", default_store_id)
        inbound_msg = (
            (dumped.get("message") or dumped.get("customer_text") or dumped.get("query") or "").strip()
        )
        inbound_msg = inbound_msg.replace("\n", " ")[:420]
        logger.info(
            "[webhook.dev] inbound intent=%r phone=%r store=%r skip_ic=%s msg_preview=%r dump_keys=%s",
            dumped.get("intent"),
            dumped.get("phone"),
            dumped.get("store_id"),
            dumped.get("skip_intent_classification"),
            inbound_msg,
            sorted(dumped.keys()),
        )
        result = orchestrator.handle(dumped)
        ia = result.get("intent_analysis") or {}
        logger.info(
            "[webhook.dev] outbound classify_intent=%s sub=%s lang=%s conf=%s reply_chars=%s has_images=%s",
            ia.get("intent"),
            ia.get("sub_intent"),
            ia.get("language"),
            ia.get("confidence"),
            len((result.get("reply") or "")),
            bool(result.get("images")),
        )
        return result

    return router
