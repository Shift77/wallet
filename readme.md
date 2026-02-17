# Wallet Service

A Django-based wallet service supporting deposits, scheduled withdrawals, and resilient third-party bank integration.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Client     │────▶│  Django API  │────▶│   Services   │
│  (REST API)  │     │   (Views)    │     │   (Business)  │
└─────────────┘     └──────────────┘     └───────┬──────┘
                                                  │
                    ┌──────────────┐     ┌────────▼──────┐
                    │  Third-Party │◀────│   Celery      │
                    │  Bank (Flask)│     │  (Tasks/Beat) │
                    └──────────────┘     └───────┬──────┘
                                                  │
                    ┌──────────────┐     ┌────────▼──────┐
                    │    Redis     │◀────│   Database    │
                    │   (Broker)   │     │   (SQLite)    │
                    └──────────────┘     └──────────────┘
```

## Design Patterns & Decisions

| Pattern | Where | Why |
|---|---|---|
| **Service Layer** | `services.py` | Separates business logic from views for testability and reuse |
| **Repository Pattern** | Model query methods | `get_due_pending_withdrawals()`, `get_failed_retryable_withdrawals()` encapsulate query logic |
| **Atomic Transactions** | `services.py` | `@transaction.atomic` + `select_for_update()` prevents race conditions |
| **F() Expressions** | Balance updates | Atomic DB-level increment/decrement — no read-modify-write races |
| **Task Queue** | Celery tasks | Deferred execution of scheduled withdrawals |
| **Retry with Backoff** | `process_single_withdrawal` | Exponential backoff for transient third-party failures |
| **Idempotent Processing** | `execute()` | Status-based guards prevent double-processing |

## Key Requirements

- **Non-negative balance**: Enforced at withdrawal execution time
- **Deferred validation**: Balance is checked when the withdrawal executes, not when it's scheduled
- **Concurrency safety**: `select_for_update()` row-level locks prevent race conditions
- **Third-party resilience**: Connection errors, timeouts, and HTTP failures are all handled with retry logic
- **Balance refund on failure**: If the third-party rejects a withdrawal, the amount is returned to the wallet

## Setup

### Prerequisites
- Python 3.10+
- Redis (running locally on port 6379)

### Install & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start the Django server
python manage.py runserver

# Start Celery worker (in a separate terminal)
celery -A wallet worker -l info

# Start Celery Beat scheduler (in a separate terminal)
celery -A wallet beat -l info

# Start the third-party bank service (in a separate terminal)
cd ../third-party
pip install flask
python app.py
```

### Run Tests

```bash
python manage.py test wallets -v2
```

## API Endpoints

### Wallet

| Method | URL | Description |
|---|---|---|
| `POST` | `/wallets/` | Create a new wallet |
| `GET` | `/wallets/<uuid>/` | Get wallet details |

### Transactions

| Method | URL | Description |
|---|---|---|
| `POST` | `/wallets/<uuid>/deposit` | Deposit into wallet |
| `POST` | `/wallets/<uuid>/withdraw` | Schedule a withdrawal |
| `GET` | `/wallets/<uuid>/transactions/` | List transactions (filterable by `?status=` and `?type=`) |
| `GET` | `/wallets/<uuid>/transactions/<id>/` | Get transaction details |

### Example: Create Wallet
```bash
curl -X POST http://localhost:8000/wallets/
```

### Example: Deposit
```bash
curl -X POST http://localhost:8000/wallets/<uuid>/deposit \
  -H "Content-Type: application/json" \
  -d '{"amount": 10000}'
```

### Example: Schedule Withdrawal
```bash
curl -X POST http://localhost:8000/wallets/<uuid>/withdraw \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000, "scheduled_for": "2026-02-15T15:00:00Z"}'
```

## Project Structure

```
wallet/
├── manage.py
├── requirements.txt
├── readme.md
├── wallet/                   # Project configuration
│   ├── settings.py           # Django + Celery + third-party config
│   ├── celery.py             # Celery app setup
│   ├── urls.py
│   └── __init__.py           # Celery app auto-import
└── wallets/                  # Main application
    ├── models.py             # Wallet & Transaction models
    ├── services.py           # WalletService & WithdrawalService
    ├── tasks.py              # Celery tasks (process/retry withdrawals)
    ├── views.py              # API views
    ├── serializers.py         # DRF serializers with validation
    ├── utils.py              # Third-party bank HTTP client
    ├── urls.py               # URL routing
    ├── admin.py              # Django admin configuration
    └── tests.py              # Comprehensive test suite
```

## Assumptions

1. Amounts are stored as integers in the smallest currency unit (e.g., Rials)
2. The third-party service returns `{"data": "success", "status": 200}` on success and `{"data": "failed", "status": 503}` on failure
3. Failed withdrawals are retried up to 3 times with exponential backoff
4. Celery Beat checks for due withdrawals every 10 seconds
