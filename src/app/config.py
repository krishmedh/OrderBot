import os

from pydantic import BaseModel
from dotenv import load_dotenv


# Auto-load .env from current working directory or parents.
load_dotenv()


class Settings(BaseModel):
    app_name: str = "WhatsApp Store Commerce"
    default_currency: str = "INR"
    app_env: str = os.getenv("APP_ENV", "development")

    # Logging (`app.logging_setup.configure_logging`)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_console: bool = os.getenv("LOG_CONSOLE", "true").lower() in ("1", "true", "yes", "on")
    log_console_level: str = os.getenv("LOG_CONSOLE_LEVEL", "INFO")
    log_file_enabled: bool = os.getenv("LOG_FILE_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    log_directory: str = os.getenv("LOG_DIRECTORY", "logs")
    log_file_name: str = os.getenv("LOG_FILE_NAME", "whatsapp-commerce.log")
    log_max_bytes: int = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    log_backup_count: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    log_format: str = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    log_datefmt: str = os.getenv("LOG_DATEFMT", "%Y-%m-%d %H:%M:%S")
    # Overrides minimum level for the rotating file handler (omit to use LOG_LEVEL).
    log_file_level: str = os.getenv("LOG_FILE_LEVEL", "").strip()
    # Log full prompts and API response bodies from OpenAI (intent + QA). Never logs HTTP headers / API keys.
    log_openai_dump_full: bool = os.getenv("LOG_OPENAI_DUMP_FULL", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    log_openai_max_chars: int = int(os.getenv("LOG_OPENAI_MAX_CHARS", "500000"))

    # WhatsApp Cloud API
    whatsapp_access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    whatsapp_api_version: str = os.getenv("WHATSAPP_API_VERSION", "v19.0")
    # Meta app dashboard: App secret — used to verify X-Hub-Signature-256 on POST webhooks.
    meta_app_secret: str = os.getenv("META_APP_SECRET", "")
    # Same as Meta "Verify token" when you configure the webhook callback URL (GET challenge).
    whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    # Legacy alias for HMAC secret (prefer META_APP_SECRET for WhatsApp Cloud API).
    webhook_verify_secret: str = os.getenv("WEBHOOK_VERIFY_SECRET", "")

    # Store contact shown when checkout or payment fails
    store_contact_phone: str = os.getenv("STORE_CONTACT_PHONE", "")

    # Payments
    payment_provider: str = os.getenv("PAYMENT_PROVIDER", "fake")
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    razorpay_key_id: str = os.getenv("RAZORPAY_KEY_ID", "")
    razorpay_key_secret: str = os.getenv("RAZORPAY_KEY_SECRET", "")

    # Database
    database_url: str = os.getenv("DATABASE_URL", "")

    # Multi-store catalog (JSON per store_id) and routing
    catalog_data_dir: str = os.getenv("CATALOG_DATA_DIR", "data/catalogs")
    # Public URL of this API (for WhatsApp image messages and absolute image links).
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    store_routing_file: str = os.getenv("STORE_ROUTING_FILE", "data/store_routing.json")
    default_store_id: str = os.getenv("DEFAULT_STORE_ID", "default")
    # Recent (user, assistant) pairs per customer+store for QA follow-ups (in-process memory).
    conversation_max_turns: int = int(os.getenv("CONVERSATION_MAX_TURNS", "12"))
    # Ollama (local): used as QA fallback when OpenAI fails, or as sole QA if no OpenAI key.
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Intent routing (OpenAI JSON classification + domain handlers; heuristic fallback)
    intent_classification_enabled: bool = os.getenv("INTENT_CLASSIFICATION_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    intent_classification_model: str = os.getenv("INTENT_CLASSIFICATION_MODEL", "gpt-4o-mini")
    intent_classification_prompt_path: str = os.getenv("INTENT_CLASSIFICATION_PROMPT_PATH", "").strip()
    intent_legacy_flow: bool = os.getenv("INTENT_LEGACY_FLOW", "false").lower() in ("1", "true", "yes", "on")

    # Catalogue vector index for intent prompt menu context (SQLite + OpenAI embeddings)
    catalog_vector_enabled: bool = os.getenv("CATALOG_VECTOR_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    catalog_vector_db_path: str = os.getenv("CATALOG_VECTOR_DB_PATH", "data/catalog_vectors.db")
    catalog_embedding_model: str = os.getenv("CATALOG_EMBEDDING_MODEL", "text-embedding-3-small")
    catalog_vector_top_k: int = int(os.getenv("CATALOG_VECTOR_TOP_K", "18"))


settings = Settings()
