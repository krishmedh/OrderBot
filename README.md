# WhatsApp Store Commerce

Modular backend service for store sales enablement over WhatsApp.  
It supports:

- Product availability queries
- Order placement
- Payment collection (pluggable gateway)
- Order cancelation
- Multilingual audio handling (English, Assamese, Hindi, Bengali)
- Generic customer Q&A over chat
- Inventory checks
- Promotional broadcast messages

## Architecture

The project uses ports-and-adapters style modules:

- `domain`: core entities and interfaces
- `services`: business logic and orchestration
- `adapters`: integrations (repositories, WhatsApp, payment, speech, LLM)
- `api`: FastAPI webhook and request parsing

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

## Environment Setup

Copy `.env.example` to `.env` and fill credentials:

- `PAYMENT_PROVIDER=fake|razorpay|stripe`
- `DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname` to enable Postgres persistence
- `WEBHOOK_VERIFY_SECRET` to enforce WhatsApp webhook signature verification
- `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` for WhatsApp Cloud API
- `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` for Razorpay
- `STRIPE_SECRET_KEY` for Stripe
- `CATALOG_DATA_DIR` (default `data/catalogs`): one JSON file per store, named `{store_id}.json`
- `STORE_ROUTING_FILE` (default `data/store_routing.json`): maps WhatsApp `phone_number_id` and display number digits → `store_id`
- `DEFAULT_STORE_ID` (default `default`) when routing does not match
- `OPENAI_API_KEY` for multilingual STT + cloud QA (optional)
- `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`) and `OLLAMA_MODEL` (e.g. `llama3.2`) for **local** QA via Ollama. If both OpenAI and Ollama are set, OpenAI is tried first; on failure or empty reply, **Ollama is used**. If only Ollama is set, QA uses Ollama only.

By default, if credentials are not set, the service uses fake adapters to keep local development and tests deterministic.

## Test

```bash
pytest
```

## Docker

```bash
docker build -t whatsapp-store-commerce .
docker run --env-file .env -p 8000:8000 whatsapp-store-commerce
```

or

```bash
docker compose up --build
```

## CI

GitHub Actions workflow at `.github/workflows/ci.yml` runs tests on every push and pull request.

## Notes

- Real adapter scaffolding is included for Meta WhatsApp Cloud API and Stripe/Razorpay payment links.
- HMAC signature validation is enforced when `WEBHOOK_VERIFY_SECRET` is configured.
- Postgres-backed repositories are used automatically when `DATABASE_URL` is set.
