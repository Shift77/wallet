# 💰 Wallet Service

A Django-based wallet service supporting **deposits**, **scheduled withdrawals**, and **resilient third-party bank integration**. Built with concurrency safety, idempotent operations, and automated retry logic.

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│   Client     │────▶│  Django API  │────▶│   Services    │
│  (REST API)  │     │   (Views)    │     │  (Business)   │
└─────────────┘     └──────────────┘     └───────┬───────┘
                                                  │
                    ┌──────────────┐     ┌────────▼───────┐
                    │  Third-Party │◀────│    Celery       │
                    │  Bank (Flask)│     │  (Tasks/Beat)   │
                    └──────────────┘     └────────┬───────┘
                                                  │
                    ┌──────────────┐     ┌────────▼───────┐
                    │    Redis     │◀────│   Database      │
                    │   (Broker)   │     │ (SQLite/MySQL)  │
                    └──────────────┘     └────────────────┘
```

### How It Works

1. **Deposits** are processed immediately and atomically — the wallet balance is updated and a `COMPLETED` transaction is recorded.
2. **Withdrawals** are scheduled for a future time. They are created with `PENDING` status.
3. **Celery Beat** periodically checks for due withdrawals (every 10s) and dispatches them to a Celery worker.
4. The worker **deducts the balance**, calls the **third-party bank service**, and marks the transaction as `COMPLETED` or `FAILED`.
5. **Failed withdrawals** are automatically retried (up to 3 times) with exponential backoff. The balance is refunded on failure.

---

## 🧩 Design Patterns & Decisions

| Pattern | Where | Why |
|---|---|---|
| **Service Layer** | `wallets/services/` | Separates business logic from views for testability and reuse |
| **Repository Pattern** | Model query methods | `get_due_pending_withdrawals()`, `get_failed_retryable_withdrawals()` encapsulate query logic |
| **Atomic Transactions** | `wallets/services/` | `@transaction.atomic` + `select_for_update()` prevents race conditions |
| **F() Expressions** | Balance updates | Atomic DB-level increment/decrement — no read-modify-write races |
| **Task Queue** | `wallets/tasks.py` | Deferred execution of scheduled withdrawals via Celery |
| **Retry with Backoff** | `process_single_withdrawal` | Exponential backoff for transient third-party failures |
| **Idempotent Operations** | Deposit & Withdrawal | Client-provided `Idempotency-Key` header prevents duplicate processing |
| **Modular App Structure** | `models/`, `views/`, `serializers/`, `services/` | Each concern is organized in its own package for clarity and scalability |

### Key Requirements

- **Non-negative balance**: Enforced via `PositiveBigIntegerField` and service-level validation
- **Deferred validation**: Balance is checked when the withdrawal *executes*, not when it's *scheduled*
- **Concurrency safety**: `select_for_update()` row-level locks prevent race conditions
- **Third-party resilience**: Connection errors, timeouts, and HTTP failures are all handled with retry logic
- **Balance refund on failure**: If the third-party rejects a withdrawal, the amount is returned to the wallet
- **Idempotency**: Duplicate requests with the same `Idempotency-Key` return the original transaction

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Redis (for Celery broker)

### Option 1: Run Locally

```bash
# 1. Clone the repository
git clone <repo-url>
cd wallet

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run database migrations
python manage.py migrate

# 5. Start the Django development server
python manage.py runserver

# 6. Start the Celery worker (in a separate terminal)
celery -A wallet worker -l info

# 7. Start the Celery Beat scheduler (in a separate terminal)
celery -A wallet beat -l info

# 8. Start the third-party bank simulator (in a separate terminal)
cd third-party
pip install flask
python app.py
```

### Option 2: Run with Docker Compose 🐳

The entire stack (Django, Celery, Redis, MySQL, third-party bank) can be launched with a single command:

```bash
docker compose up --build
```

This starts the following services:

| Service | Port | Description |
|---|---|---|
| `backend` | `8000` | Django API server (Gunicorn) |
| `celery` | — | Celery worker for async task processing |
| `celery-beat` | — | Celery Beat for periodic task scheduling |
| `third-party` | `8010` | Flask-based third-party bank simulator |
| `redis` | `6379` | Message broker for Celery |
| `db` | `3306` | MySQL 8.0 database |

---

## 🧪 Running Tests

The project includes a comprehensive test suite covering models, services, API endpoints, and Celery tasks (44 tests).

```bash
# Run all tests
python manage.py test wallets -v2

# Run a specific test class
python manage.py test wallets.tests.WalletServiceTest -v2

# Run a single test
python manage.py test wallets.tests.WithdrawalServiceTest.test_execute_success -v2
```

### Test Coverage

| Area | Tests | What's Covered |
|---|---|---|
| **Models** | 7 | Wallet/Transaction creation, UUID uniqueness, query methods |
| **Services** | 12 | Deposits, withdrawals, idempotency, insufficient balance, third-party failures, refunds |
| **API** | 19 | All endpoints, validation errors, edge cases, idempotency headers |
| **Celery Tasks** | 3 | Pending withdrawal processing, single withdrawal execution, failed retry dispatch |

---

## 📡 API Reference

### Wallet Endpoints

| Method | URL | Description |
|---|---|---|
| `POST` | `/wallets/` | Create a new wallet |
| `GET` | `/wallets/<uuid>/` | Get wallet details |

### Transaction Endpoints

| Method | URL | Description |
|---|---|---|
| `POST` | `/wallets/<uuid>/deposit` | Deposit into wallet |
| `POST` | `/wallets/<uuid>/withdraw` | Schedule a withdrawal |
| `GET` | `/wallets/<uuid>/transactions/` | List transactions (filterable) |
| `GET` | `/wallets/<uuid>/transactions/<id>/` | Get transaction details |

### Transaction Filters

The transaction list endpoint supports query parameters:

- `?status=PENDING` — Filter by status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`)
- `?type=DEPOSIT` — Filter by type (`DEPOSIT`, `WITHDRAWAL`)

### Idempotency

Both deposit and withdrawal endpoints support idempotency. Pass a UUID in the `Idempotency-Key` HTTP header:

```bash
curl -X POST http://localhost:8000/wallets/<uuid>/deposit \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"amount": 10000}'
```

Duplicate requests with the same key will return the original transaction without re-processing.

### Example Requests

**Create a wallet:**
```bash
curl -X POST http://localhost:8000/wallets/
```
```json
{
  "uuid": "a1b2c3d4-...",
  "balance": 0,
  "created_at": "2026-02-17T10:00:00Z"
}
```

**Deposit:**
```bash
curl -X POST http://localhost:8000/wallets/<uuid>/deposit \
  -H "Content-Type: application/json" \
  -d '{"amount": 10000}'
```
```json
{
  "wallet": { "uuid": "a1b2c3d4-...", "balance": 10000 },
  "transaction": {
    "id": 1,
    "amount": 10000,
    "transaction_type": "DEPOSIT",
    "status": "COMPLETED",
    "executed_at": "2026-02-17T10:01:00Z"
  }
}
```

**Schedule a withdrawal:**
```bash
curl -X POST http://localhost:8000/wallets/<uuid>/withdraw \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000, "scheduled_for": "2026-02-17T12:00:00Z"}'
```
```json
{
  "id": 2,
  "amount": 5000,
  "transaction_type": "WITHDRAWAL",
  "status": "PENDING",
  "scheduled_for": "2026-02-17T12:00:00Z"
}
```

---

## 📁 Project Structure

```
wallet/
├── manage.py                          # Django management script
├── requirements.txt                   # Python dependencies
├── Dockerfile                         # Docker image for the Django app
├── docker-compose.yaml                # Full stack orchestration
├── .pre-commit-config.yaml            # Pre-commit hooks (Black + tests)
│
├── wallet/                            # Django project configuration
│   ├── settings.py                    # Django, Celery, third-party config
│   ├── celery.py                      # Celery app setup + autodiscover
│   ├── urls.py                        # Root URL configuration
│   ├── wsgi.py                        # WSGI entry point
│   └── __init__.py                    # Celery app auto-import
│
├── wallets/                           # Main application
│   ├── models/                        # Database models
│   │   ├── base.py                    # Abstract base model (created_at, updated_at)
│   │   ├── wallet.py                  # Wallet model (UUID, balance)
│   │   └── transaction.py             # Transaction model (deposits & withdrawals)
│   │
│   ├── services/                      # Business logic layer
│   │   ├── wallet.py                  # WalletService (deposit with concurrency safety)
│   │   └── withdrawal.py             # WithdrawalService (schedule, execute, refund)
│   │
│   ├── serializers/                   # DRF serializers
│   │   ├── wallet.py                  # Wallet serializer
│   │   ├── deposit.py                 # Deposit request validation
│   │   ├── withdraw.py                # Withdrawal request validation
│   │   └── transaction.py             # Transaction serializer
│   │
│   ├── views/                         # API views
│   │
│   ├── utils/                         # Utilities
│   │   └── third_party.py             # HTTP client for third-party bank
│   │
│   ├── management/commands/
│   │   └── wait_for_db.py             # Custom command to wait for DB readiness
│   │
│   ├── tasks.py                       # Celery tasks (process/retry withdrawals)
│   ├── urls.py                        # URL routing for wallet endpoints
│   ├── admin.py                       # Django admin configuration
│   └── tests.py                       # Comprehensive test suite (44 tests)
│
└── third-party/                       # Third-party bank simulator
    ├── Dockerfile                     # Docker image for the Flask app
    └── app.py                         # Flask app simulating bank API
```

---

## 🔧 Configuration

Key settings are configurable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `DB_ENGINE` | `django.db.backends.sqlite3` | Database engine |
| `DB_NAME` | `db.sqlite3` | Database name |
| `DB_USER` | — | Database user |
| `DB_PASSWORD` | — | Database password |
| `DB_HOST` | — | Database host |
| `DB_PORT` | — | Database port |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker URL |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Celery result backend |
| `THIRD_PARTY_BASE_URL` | `http://localhost:8010` | Third-party bank service URL |

---

## 🛡️ Pre-commit Hooks

This project uses [pre-commit](https://pre-commit.com/) to enforce code quality on every commit:

1. **Black** — Automatically formats all Python files
2. **Django Tests** — Runs the full test suite; commit is blocked if any test fails

### Setup (first time only)

```bash
pip install pre-commit
pre-commit install
```

### How it works

```
git commit -m "your message"
       │
       ▼
  ① Black formats all .py files
       │── If files changed → commit blocked, re-stage & retry
       │── If no changes   → ✅ pass
       ▼
  ② Django tests run (manage.py test)
       │── If any test fails → ❌ commit blocked
       │── If all pass       → ✅ commit proceeds
```

### Manual run

```bash
# Run all hooks on every file
pre-commit run --all-files

# Skip hooks in an emergency
git commit --no-verify -m "hotfix"
```

---

## 📝 Assumptions

1. Amounts are stored as **integers in the smallest currency unit** (e.g., Rials) to avoid floating-point precision issues
2. The third-party bank service returns `{"data": "success", "status": 200}` on success and `{"data": "failed", "status": 503}` on failure
3. Failed withdrawals are retried up to **3 times** with exponential backoff
4. Celery Beat checks for due withdrawals every **10 seconds** and retries failed ones every **60 seconds**
5. **No authentication** is required for API access (as per the task scope)
6. Balance is validated at **execution time**, not at scheduling time — a user may schedule a withdrawal larger than their current balance if they expect future deposits
