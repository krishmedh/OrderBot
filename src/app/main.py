from contextlib import asynccontextmanager
import logging
from pathlib import Path

from app.logging_setup import configure_logging

configure_logging()

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.factory import (
    get_payment_gateway,
    get_qa_provider,
    get_repositories,
    get_stt_provider,
    get_whatsapp_gateway,
)
from app.adapters.store_routing import load_store_routing
from app.api.webhook import create_router
from app.config import settings
from app.services.audio_service import AudioService
from app.services.inventory_service import InventoryService
from app.services.orchestrator import CommerceOrchestrator
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.promo_service import PromotionService
from app.services.qa_service import QAService
from app.services.intent_classifier import IntentClassifierService
from app.services.product_media import catalog_images_dir, set_catalog_images_dir
from app.services.store_inventory_locator import StoreInventoryLocator


@asynccontextmanager
async def lifespan(app: FastAPI):
    lvl = getattr(logging, (settings.log_level or "INFO").upper(), logging.INFO)
    if not isinstance(lvl, int):
        lvl = logging.INFO

    svc_level = lvl
    if settings.log_openai_dump_full:
        svc_level = min(svc_level, logging.INFO)

    ic_level = logging.DEBUG if settings.log_openai_dump_full else svc_level
    qa_level = logging.DEBUG if settings.log_openai_dump_full else svc_level

    for name in (
        "app.api.webhook",
        "app.services.orchestrator",
        "app.services.intent_context",
        "app.services.intent_handlers.router",
    ):
        logging.getLogger(name).setLevel(svc_level)

    logging.getLogger("app.services.intent_classifier").setLevel(ic_level)
    logging.getLogger("app.adapters.http_integrations").setLevel(qa_level)

    if settings.catalog_vector_enabled and (settings.openai_api_key or "").strip():
        try:
            from app.services.catalog_vector_store import ensure_store_indexed

            ensure_store_indexed(inventory_service, settings.default_store_id)
        except Exception:
            logging.getLogger(__name__).exception("Catalog vector index warm-up failed")

    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

catalog_dir = Path(settings.catalog_data_dir)
if not catalog_dir.is_absolute():
    catalog_dir = Path.cwd() / catalog_dir
routing_path = Path(settings.store_routing_file)
if not routing_path.is_absolute():
    routing_path = Path.cwd() / routing_path

catalog_dir.mkdir(parents=True, exist_ok=True)
_images_dir = catalog_dir / "images"
_images_dir.mkdir(parents=True, exist_ok=True)
set_catalog_images_dir(_images_dir)
store_routing_data = load_store_routing(routing_path)

inventory_repo_fallback, order_repo = get_repositories()
store_locator = StoreInventoryLocator(
    catalog_dir,
    settings.default_store_id,
    fallback=inventory_repo_fallback,
    prefer_database_inventory=bool(settings.database_url.strip()),
)

whatsapp_gateway = get_whatsapp_gateway()
payment_gateway = get_payment_gateway()
qa_provider = get_qa_provider()
stt_provider = get_stt_provider()

inventory_service = InventoryService(store_locator)
order_service = OrderService(store_locator, order_repo)
payment_service = PaymentService(order_repo, payment_gateway)
qa_service = QAService(qa_provider)
audio_service = AudioService(stt_provider)
promotion_service = PromotionService(whatsapp_gateway)

intent_classifier_service = IntentClassifierService()

orchestrator = CommerceOrchestrator(
    inventory_service=inventory_service,
    order_service=order_service,
    payment_service=payment_service,
    qa_service=qa_service,
    audio_service=audio_service,
    promotion_service=promotion_service,
    intent_classifier=intent_classifier_service,
)

app.include_router(
    create_router(
        orchestrator,
        whatsapp_gateway,
        store_routing_data,
        settings.default_store_id,
    )
)

_CHAT_STATIC = Path(__file__).resolve().parent / "static" / "chat"


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/chat", status_code=302)


@app.get("/chat")
def chat_page() -> FileResponse:
    return FileResponse(_CHAT_STATIC / "index.html")


app.mount("/chat/assets", StaticFiles(directory=_CHAT_STATIC), name="chat-assets")
app.mount("/catalog/images", StaticFiles(directory=_images_dir), name="catalog-images")
