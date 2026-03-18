# payment-service

Payment Service for the DLS-2 food delivery platform. Processes payments for incoming orders via Kafka events and publishes payment results back to Kafka.

## Tech Stack

- **Framework:** FastAPI (Python 3.12)
- **Database:** PostgreSQL (SQLAlchemy ORM)
- **Messaging:** Apache Kafka (aiokafka)
- **CI/CD:** GitHub Actions with shared workflows → GHCR

## How It Works

This service is **event-driven** — payments are not created via REST. Instead:

1. Order Service publishes an `OrderCreated` event to the `orders` Kafka topic
2. Payment Service consumes the event, simulates payment processing, and saves the result to PostgreSQL
3. Payment Service publishes `PaymentAuthorized` or `PaymentFailed` to the `payments` Kafka topic
4. Order Service consumes the result and updates the order status

The REST API is read-only — it lets other services and the frontend check payment status.

### Payment Simulation

Payments are simulated using test card numbers (similar to Stripe's test mode). The last 4 digits of the card number determine the outcome:

| Last 4 digits | Result | Reason |
|---------------|--------|--------|
| `0000` | Success | Payment authorized |
| `9999` | Declined | Insufficient funds |
| `5555` | Declined | Card expired |
| `1111` | Declined | Card reported stolen |
| Any other | Success | Payment authorized |

Business rules applied regardless of card: amounts over 10,000 or less than/equal to 0 always fail.

## API

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| GET | `/v1/payments/` | List all payments (with pagination) |
| GET | `/v1/payments/{id}` | Get payment by UUID |
| GET | `/v1/payments/order/{order_id}` | Get payments for a specific order |

### Kafka Events

**Consumes** from `orders` topic:

- `OrderCreated` — triggers payment processing

**Produces** to `payments` topic:

- `PaymentAuthorized` — payment succeeded, order can proceed
- `PaymentFailed` — payment failed, order should be cancelled

## Project Structure

```
payment-service/
├── app/
│   ├── routers/
│   │   └── payments.py        # REST endpoints (read-only)
│   ├── config.py              # Settings from environment variables
│   ├── database.py            # SQLAlchemy engine and session setup
│   ├── events.py              # Kafka event schemas (Pydantic models)
│   ├── kafka_consumer.py      # Consumes OrderCreated, processes payments
│   ├── kafka_producer.py      # Publishes payment results to Kafka
│   ├── main.py                # FastAPI app entry point
│   ├── models.py              # Database table definitions
│   └── schemas.py             # Pydantic request/response models
├── tests/
│   ├── conftest.py            # Test fixtures (SQLite + mocked Kafka)
│   ├── test_payments.py       # REST endpoint tests
│   └── test_processing.py     # Payment simulation logic tests
├── .github/workflows/
│   ├── tollgate.yaml          # Quality gate on PRs
│   └── build.yaml             # Build + push on merge to main
├── docker-compose.yaml        # Local dev: PostgreSQL (Kafka runs in infra repo)
├── Dockerfile                 # Multi-stage production build
└── pyproject.toml             # Dependencies and versioning
```

## Development

Requires Kafka running from the infra repo:

```bash
# Terminal 1 — start Kafka (from infra repo)
cd ../infra/docker
docker compose -f docker-compose.kafka.yaml up -d

# Terminal 2 — start PostgreSQL and run the service
cd payment-service
docker compose up postgres -d
poetry install
poetry run uvicorn app.main:app --port 8003 --reload
```

- Swagger UI: http://localhost:8003/docs

## Run Tests

Tests use SQLite in-memory and mock Kafka — no infrastructure needed:

```bash
poetry run pytest -v
```

## CI/CD

Automated via GitHub Actions using shared workflows from `DLS-soft2/shared-workflows`:

- **On PR to main:** Pylint linting, pytest, version bump check
- **On merge to main:** Docker image built and pushed to `ghcr.io/dls-soft2/payment-service:<version>`
