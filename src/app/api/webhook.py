import json
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request
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


def create_router(
    orchestrator: CommerceOrchestrator,
    whatsapp_gateway: WhatsAppGateway,
    store_routing: dict,
    default_store_id: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/webhook/whatsapp")
    def verify_whatsapp_webhook(
        hub_mode: str | None = Query(None, alias="hub.mode"),
        hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
        hub_challenge: str | None = Query(None, alias="hub.challenge"),
    ):
        """Meta WhatsApp Cloud API subscription verification (required once per callback URL)."""
        if hub_mode == "subscribe" and hub_verify_token and settings.whatsapp_verify_token:
            if hub_verify_token == settings.whatsapp_verify_token:
                return PlainTextResponse(content=hub_challenge or "", status_code=200)
        raise HTTPException(status_code=403, detail="Verification failed.")

    @router.post("/webhook/whatsapp")
    async def receive_whatsapp_event(
        request: Request,
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
                store_id = resolve_store_id(metadata, store_routing, default_store_id)
                logger.info("WhatsApp webhook inbound: %s", _summarize_meta_message(msg))
                payload = message_to_orchestrator_payload(wa_from, msg, store_id)
                logger.info(
                    "WhatsApp webhook mapped intent=%s phone=%s keys=%s",
                    payload.get("intent"),
                    payload.get("phone", wa_from),
                    sorted(k for k in payload if k not in ("message",) and payload.get(k) is not None),
                )
                if payload.get("message"):
                    mq = str(payload["message"])
                    logger.info("WhatsApp webhook customer text (truncated): %s", mq[:800] + ("…" if len(mq) > 800 else ""))
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
                        whatsapp_gateway.send_message(wa_from, reply_text[:4096])
                    except Exception:
                        logger.exception("WhatsApp send_message failed for to=%s", wa_from)
                for img in (result.get("images") or [])[:3]:
                    try:
                        whatsapp_gateway.send_image(
                            wa_from,
                            img["url"],
                            img.get("caption") or "",
                        )
                    except Exception:
                        logger.exception(
                            "WhatsApp send_image failed for to=%s url=%s",
                            wa_from,
                            img.get("url"),
                        )
                if not reply_text and not result.get("images"):
                    logger.warning("WhatsApp webhook no reply generated for from=%s intent=%s", wa_from, payload.get("intent"))
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
