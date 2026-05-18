"""OpenAI-backed per-item intent classification with heuristic fallback."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import httpx

from app.config import settings
from app.domain.intent_classification import (
    IntentClassification,
    ItemIntent,
    normalize_sub_intent,
)
from app.logging_setup import format_json_for_log, truncate_for_log
from app.services.cart_commands import (
    parse_remove_target,
    parse_update_command,
    wants_clear_cart,
    wants_show_cart,
)
from app.services.assamese_grocery_lexicon import (
    apply_assamese_lexicon,
    detect_assamese_products,
    detect_product_availability_query,
    is_open_catalogue_question,
)
from app.services.intent_context import format_previous_message_block
from app.services.menu_commands import is_menu_command, looks_like_menu_request
from app.services.shopping_intent_signals import looks_like_open_ended_shopping_without_product
from app.services.shopping_session import parse_shopping_confirmation, wants_cart_checkout

logger = logging.getLogger(__name__)
_dump = logging.getLogger("app.openai.intent")

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "intent_classification.txt"
_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_COMMA_LIST = re.compile(r"\s*[,;]\s*")


def _load_prompt_template(path: Path | None = None) -> str:
    p = path or Path(settings.intent_classification_prompt_path or _PROMPT_PATH)
    if not p.is_file():
        logger.warning("Intent prompt file missing at %s", p)
        return ""
    return p.read_text(encoding="utf-8")


def _extract_json_object(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _parse_items_dict(raw: object) -> dict[str, ItemIntent]:
    items: dict[str, ItemIntent] = {}
    if not isinstance(raw, dict):
        return items
    for key, val in raw.items():
        k = str(key).strip().lower()
        if not k:
            continue
        parsed = ItemIntent.from_raw(val, item_key=k)
        if parsed is not None:
            items[k] = parsed
    return items


def _parse_classification_dict(data: dict) -> IntentClassification | None:
    try:
        items = _parse_items_dict(data.get("items"))
        # Legacy top-level intent block → single item
        if not items and data.get("sub_intent"):
            sub = normalize_sub_intent(str(data.get("sub_intent")))
            ent = data.get("entities") or {}
            names = list(ent.get("items") or []) if isinstance(ent, dict) else []
            qtys = list(ent.get("quantities") or []) if isinstance(ent, dict) else []
            if names:
                for i, name in enumerate(names):
                    k = str(name).strip().lower()
                    if not k:
                        continue
                    q = str(qtys[i]).strip() if i < len(qtys) else ""
                    items[k] = ItemIntent(
                        intent="grocery",
                        sub_intent=sub,
                        quantity=q,
                        normalized_query=str(data.get("normalized_query") or ""),
                    )
            else:
                items["_message"] = ItemIntent(
                    intent="grocery",
                    sub_intent=sub,
                    quantity="",
                    normalized_query=str(data.get("normalized_query") or ""),
                )
        conf = data.get("confidence")
        try:
            c = float(conf) if conf is not None else 0.85
        except (TypeError, ValueError):
            c = 0.85
        return IntentClassification(
            language=str(data.get("language") or "en"),
            urgency=str(data.get("urgency") or "LOW"),
            items=items,
            confidence=max(0.0, min(1.0, c)),
            context_used=str(data.get("context_used") or "current"),
        )
    except Exception:
        logger.exception("Failed to parse classification dict")
        return None


def _split_product_clauses(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = [p.strip() for p in _COMMA_LIST.split(t) if p.strip()]
    return parts if len(parts) >= 2 else []


def _heuristic_items(text: str) -> dict[str, ItemIntent]:
    t = (text or "").strip()
    low = t.lower()

    if is_menu_command(t) or looks_like_menu_request(t):
        return {
            "menu": ItemIntent(
                intent="grocery",
                sub_intent="query_items",
                normalized_query="Show catalogue menu",
            )
        }

    if wants_clear_cart(t):
        return {
            "clear_cart": ItemIntent(
                intent="grocery",
                sub_intent="delete_cart",
                normalized_query="Clear shopping cart",
            )
        }

    if wants_show_cart(t):
        return {
            "cart": ItemIntent(
                intent="grocery",
                sub_intent="view_cart",
                normalized_query="Show shopping cart",
            )
        }

    if wants_cart_checkout(t):
        return {
            "checkout": ItemIntent(
                intent="grocery",
                sub_intent="checkout",
                normalized_query="Checkout and place order",
            )
        }

    rem = parse_remove_target(t)
    if rem:
        return {
            rem.lower(): ItemIntent(
                intent="grocery",
                sub_intent="remove_from_cart",
                normalized_query=f"Remove {rem} from cart",
            )
        }

    upd = parse_update_command(t)
    if upd:
        item_q, new_val = upd
        return {
            item_q.lower(): ItemIntent(
                intent="grocery",
                sub_intent="modify_item_from_cart",
                quantity=new_val,
                normalized_query=f"Update {item_q} to {new_val}",
            )
        }

    if looks_like_open_ended_shopping_without_product(t):
        return {
            "help": ItemIntent(
                intent="grocery",
                sub_intent="general_enquiry",
                normalized_query=t,
            )
        }

    avail = detect_product_availability_query(t)
    if avail:
        return {
            avail: ItemIntent(
                intent="grocery",
                sub_intent="query_items",
                normalized_query=f"Check if {avail} are available",
            )
        }

    if is_open_catalogue_question(t):
        return {
            "catalogue": ItemIntent(
                intent="grocery",
                sub_intent="query_items",
                normalized_query="What products are available in the store?",
            )
        }

    as_products = detect_assamese_products(t)
    if as_products:
        out: dict[str, ItemIntent] = {}
        for key, label in as_products:
            out[key] = ItemIntent(
                intent="grocery",
                sub_intent="add_to_cart",
                quantity="",
                normalized_query=f"Add {label} to cart",
            )
        return out

    clauses = _split_product_clauses(t)
    if clauses:
        out: dict[str, ItemIntent] = {}
        for clause in clauses:
            key = clause.lower()
            out[key] = ItemIntent(
                intent="grocery",
                sub_intent="add_to_cart",
                quantity="",
                normalized_query=f"Add {clause} to cart",
            )
        return out

    if parse_shopping_confirmation(t)[0] or re.match(r"^\s*\d{1,3}\s*[.!?]?$", t):
        return {
            "_confirm": ItemIntent(
                intent="grocery",
                sub_intent="add_to_cart",
                normalized_query=t,
            )
        }

    return {
        t.lower(): ItemIntent(
            intent="grocery",
            sub_intent="add_to_cart",
            quantity="",
            normalized_query=f"Add {t} to cart",
        )
    }


class HeuristicIntentClassifier:
    def classify(
        self,
        history: list[tuple[str, str]],
        current_message: str,
        *,
        log_context: dict | None = None,
    ) -> IntentClassification:
        text = (current_message or "").strip()
        lc = dict(log_context or {})
        prev_block = format_previous_message_block(history)
        ctx_used = "both" if prev_block != "(no prior turns in this conversation)" else "current"
        items = _heuristic_items(text)
        logger.info(
            "[intent.heuristic] phone=%r store=%r items=%s msg_preview=%r",
            lc.get("phone", ""),
            lc.get("store_id", ""),
            list(items.keys()),
            text[:200],
        )
        return IntentClassification(
            language="en",
            urgency="LOW",
            items=items,
            confidence=0.8,
            context_used=ctx_used,
        )


class OpenAIIntentClassifier:
    def __init__(
        self,
        api_key: str,
        *,
        model: str | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model or settings.intent_classification_model
        self._prompt_path = prompt_path
        self._template: str | None = None
        self._heuristic = HeuristicIntentClassifier()

    def _get_template(self) -> str:
        if self._template is None:
            self._template = _load_prompt_template(self._prompt_path)
        return self._template

    def classify(
        self,
        history: list[tuple[str, str]],
        current_message: str,
        *,
        log_context: dict | None = None,
    ) -> IntentClassification:
        lc = dict(log_context or {})
        template = self._get_template()
        if not template.strip():
            return self._heuristic.classify(history, current_message, log_context=log_context)

        prev = format_previous_message_block(history)
        cur = (current_message or "").strip()
        menu_context = str(lc.get("menu_context") or "(catalogue hints unavailable)")
        user_content = (
            template.replace("{previous_message}", prev)
            .replace("{current_message}", cur)
            .replace("{menu_context}", menu_context)
        )

        logger.info(
            "[intent.openai] request phone=%r store=%r model=%s hist_turn_pairs=%s "
            "prompt_chars=%s current_preview=%r",
            lc.get("phone", ""),
            lc.get("store_id", ""),
            self.model,
            len(history),
            len(user_content),
            cur[:300],
        )

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a strict JSON emitter. Output exactly one JSON object, no markdown, no explanation.",
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        if settings.log_openai_dump_full:
            _dump.info(
                "[openai.dump.intent] PROMPT phone=%r store=%r\n%s",
                lc.get("phone", ""),
                lc.get("store_id", ""),
                truncate_for_log(user_content),
            )
            _dump.info(
                "[openai.dump.intent] REQUEST phone=%r store=%r\n%s",
                lc.get("phone", ""),
                lc.get("store_id", ""),
                format_json_for_log(dict(payload)),
            )
        try:
            t_req = time.monotonic()
            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=45.0,
            )
            elapsed_ms = (time.monotonic() - t_req) * 1000.0
            logger.info(
                "[intent.openai] http_received phone=%r store=%r status=%s elapsed_ms=%.1f",
                lc.get("phone", ""),
                lc.get("store_id", ""),
                response.status_code,
                elapsed_ms,
            )
            try:
                body = response.json()
            except ValueError:
                body = None
            if settings.log_openai_dump_full and isinstance(body, dict):
                _dump.info(
                    "[openai.dump.intent] RESPONSE phone=%r store=%r status=%s\n%s",
                    lc.get("phone", ""),
                    lc.get("store_id", ""),
                    response.status_code,
                    format_json_for_log(body),
                )
            response.raise_for_status()
            if not isinstance(body, dict):
                raise ValueError("OpenAI chat/completions returned non-object JSON body")
            choices = body.get("choices") or []
            message = (choices[0].get("message") if choices else {}) or {}
            content = (message.get("content") or "").strip()
            parsed = _extract_json_object(content)
            if parsed is None:
                logger.warning("[intent.openai] json_extract_failed → heuristic")
                return self._heuristic.classify(history, current_message, log_context=log_context)
            classification = _parse_classification_dict(parsed)
            if classification is None:
                return self._heuristic.classify(history, current_message, log_context=log_context)
            logger.info(
                "[intent.openai] classify_ok phone=%r store=%r items=%s urgency=%s lang=%s",
                lc.get("phone", ""),
                lc.get("store_id", ""),
                list(classification.items.keys()),
                classification.urgency,
                classification.language,
            )
            return classification
        except Exception as exc:
            logger.warning("[intent.openai] failed (%s) → heuristic", exc)
            return self._heuristic.classify(history, current_message, log_context=log_context)


class IntentClassifierService:
    def __init__(self) -> None:
        api_key = (settings.openai_api_key or "").strip()
        if api_key and settings.intent_classification_enabled:
            self._backend: HeuristicIntentClassifier | OpenAIIntentClassifier = OpenAIIntentClassifier(
                api_key
            )
        else:
            self._backend = HeuristicIntentClassifier()

    def classify(
        self,
        history: list[tuple[str, str]],
        current_message: str,
        *,
        log_context: dict | None = None,
    ) -> IntentClassification:
        t0 = time.monotonic()
        logger.info(
            "[intent.pipeline] start backend=%s phone=%r store=%r hist_pairs=%s msg_preview=%r",
            type(self._backend).__name__,
            (log_context or {}).get("phone", ""),
            (log_context or {}).get("store_id", ""),
            len(history),
            (current_message or "")[:200],
        )
        out = self._backend.classify(history, current_message, log_context=log_context)
        out = apply_assamese_lexicon(out, current_message)
        logger.info(
            "[intent.pipeline] done backend=%s elapsed_ms=%.1f items=%s",
            type(self._backend).__name__,
            (time.monotonic() - t0) * 1000.0,
            list(out.items.keys()),
        )
        return out
