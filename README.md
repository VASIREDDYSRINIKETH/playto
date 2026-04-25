# Fintech Payout Engine

A highly concurrent, idempotent, and transactional payout engine.

## Core Features
1. **Integer precision Ledger**: Balances computed at DB level using BigIntegerField representing Paise. No floats.
2. **Strict Concurrency**: Postgres row-level locks prevent race conditions during payout holds.
3. **Idempotence**: `Idempotency-Key` header prevents duplicate payouts and avoids overlapping requests.
4. **State Machine**: Strict state validation prevents invalid transitions.
5. **Background Workers**: Django-Q natively using PostgreSQL for asynchronous payouts. Incorporates retries with backoff and graceful auto-refunds on failure. No Redis required!

## Setup Instructions

### Prerequisites
- Python 3.10+
- Node.js
- PostgreSQL server running locally

### Local Setup

1. Ensure your local PostgreSQL server is running and you have a database named `payout_db` (or modify `DATABASES` settings in `settings.py`).
2. Create virtual environment and install requirements:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Set environment variables in `.env` (or run with defaults).
4. Run migrations:
   ```bash
   python manage.py migrate
   ```
5. Seed a test merchant:
   ```bash
   python manage.py shell -c "from api.models import Merchant, Ledger; m=Merchant.objects.create(name='Test Merchant'); Ledger.objects.create(merchant=m, amount=10000000, entry_type='CREDIT', purpose='INITIAL_TEST_DEPOSIT'); print('Merchant created:', m.id)"
   ```
6. Start Server:
   ```bash
   python manage.py runserver
   ```
7. Start Django-Q worker in a new terminal for background jobs:
   ```bash
   python manage.py qcluster
   ```

### Running the Frontend
```bash
cd frontend
npm install
npm run dev
```

## API Documentation

### Create Payout
`POST /api/v1/payouts/`

**Headers:**
- `Idempotency-Key`: UUID (Required)

**Body:**
```json
{
  "merchant": "<merchant_uuid>",
  "amount": 50000
}
```
