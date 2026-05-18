from app.adapters.fake_integrations import (
    FakePaymentGateway,
    FakeQAProvider,
    FakeSpeechToTextProvider,
    FakeWhatsAppGateway,
)
from app.adapters.http_integrations import (
    OpenAIQAProvider,
    OpenAISpeechToTextProvider,
    OllamaQAProvider,
    RazorpayPaymentGateway,
    StripePaymentGateway,
    WhatsAppCloudGateway,
)
from app.adapters.in_memory_repositories import InMemoryInventoryRepository, InMemoryOrderRepository
from app.adapters.qa_chain import OpenAIThenOllamaQA
from app.adapters.db import create_session_factory
from app.adapters.sql_repositories import SqlInventoryRepository, SqlOrderRepository
from app.config import settings
from app.domain.interfaces import (
    InventoryRepository,
    OrderRepository,
    PaymentGateway,
    QAProvider,
    SpeechToTextProvider,
    WhatsAppGateway,
)


def get_whatsapp_gateway() -> WhatsAppGateway:
    if settings.whatsapp_access_token and settings.whatsapp_phone_number_id:
        return WhatsAppCloudGateway(
            access_token=settings.whatsapp_access_token,
            phone_number_id=settings.whatsapp_phone_number_id,
            api_version=settings.whatsapp_api_version,
        )
    return FakeWhatsAppGateway()


def get_payment_gateway() -> PaymentGateway:
    provider = settings.payment_provider.lower()
    if provider == "stripe" and settings.stripe_secret_key:
        return StripePaymentGateway(settings.stripe_secret_key)
    if provider == "razorpay" and settings.razorpay_key_id and settings.razorpay_key_secret:
        return RazorpayPaymentGateway(settings.razorpay_key_id, settings.razorpay_key_secret)
    return FakePaymentGateway()


def get_qa_provider() -> QAProvider:
    fake = FakeQAProvider()
    ollama: OllamaQAProvider | None = None
    if settings.ollama_model.strip():
        ollama = OllamaQAProvider(settings.ollama_base_url, settings.ollama_model.strip())
    openai: OpenAIQAProvider | None = None
    if settings.openai_api_key.strip():
        openai = OpenAIQAProvider(settings.openai_api_key.strip())
    if openai is not None and ollama is not None:
        return OpenAIThenOllamaQA(openai, ollama, fake)
    if openai is not None:
        return openai
    if ollama is not None:
        return ollama
    return fake


def get_stt_provider() -> SpeechToTextProvider:
    if settings.openai_api_key:
        return OpenAISpeechToTextProvider(settings.openai_api_key)
    return FakeSpeechToTextProvider()


def get_repositories() -> tuple[InventoryRepository, OrderRepository]:
    if settings.database_url:
        session_factory = create_session_factory(settings.database_url)
        return SqlInventoryRepository(session_factory), SqlOrderRepository(session_factory)
    return InMemoryInventoryRepository(), InMemoryOrderRepository()
