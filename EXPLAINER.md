# Payout Engine Architecture & Explanations

## 1. Ledger Query

To compute the strict merchant balance without floating point errors and without iterating in Python, we use the database `SUM` aggregation natively.

**Django ORM:**
```python
from django.db.models import Sum
from django.db.models.functions import Coalesce

# We sum all credits and all debits, defaulting to 0 if none exist.
totals = Ledger.objects.filter(merchant=merchant_instance).aggregate(
    credits=Coalesce(Sum('amount', filter=Q(entry_type='CREDIT')), 0),
    debits=Coalesce(Sum('amount', filter=Q(entry_type='DEBIT')), 0)
)
balance = totals['credits'] - totals['debits']
```

**Exact SQL generated:**
```sql
SELECT 
    COALESCE(SUM("api_ledger"."amount") FILTER (WHERE "api_ledger"."entry_type" = 'CREDIT'), 0) AS "credits", 
    COALESCE(SUM("api_ledger"."amount") FILTER (WHERE "api_ledger"."entry_type" = 'DEBIT'), 0) AS "debits" 
FROM "api_ledger" 
WHERE "api_ledger"."merchant_id" = '<merchant_id>'
```

## 2. Concurrency Lock Implementation

To ensure two simultaneous payout requests don't overspend the balance, we use PostgreSQL's `SELECT ... FOR UPDATE` via Django's `select_for_update()`.

```python
from django.db import transaction

with transaction.atomic():
    # Lock the merchant row until this transaction completes or rolls back.
    # Other concurrent requests trying to fetch this merchant will wait here.
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    
    # Now we compute the balance. It is perfectly consistent.
    balance = get_merchant_balance(merchant)
    
    if balance >= payout_amount:
        # Hold funds atomically by writing a DEBIT into the ledger
        Ledger.objects.create(merchant=merchant, amount=payout_amount, entry_type='DEBIT')
        # Create Payout
        Payout.objects.create(...)
```

## 3. Idempotency Handling Logic

Idempotency correctly prevents double processing when identical requests arrive due to retries or network faults. 

Process:
1. Extract `Idempotency-Key` from headers.
2. Inside an atomic transaction window, try to `get_or_create` the key.
3. If the key already exists:
    - If `status_code` is already set: return the heavily cached response.
    - If `status_code` is `None`: a request is currently being processed with this key (race condition). Return a 409 Conflict.
4. If it's a new key, process the request synchronously (create payout).
5. At the end of the request middleware or view logic, update the idempotency key with the generated response body and `status_code`.

## 4. State Machine Enforcement

We prevent arbitrary and dangerous status changes (like `FAILED` to `COMPLETED`) via a centralized service function. Attempting direct DB mutations is blocked in the service layer.

```python
VALID_TRANSITIONS = {
    'PENDING': ['PROCESSING', 'FAILED'],
    'PROCESSING': ['COMPLETED', 'FAILED'],
    'COMPLETED': [],  # terminal
    'FAILED': []      # terminal
}

def transition_status(payout, new_status):
    if new_status not in VALID_TRANSITIONS[payout.status]:
        raise ValueError(f"Invalid transition from {payout.status} to {new_status}")
    
    payout.status = new_status
    payout.save(update_fields=['status', 'updated_at'])
```

## 5. AI Mistake Example & Correction

**Common AI Mistake:** Updating balance using a cached field and an integer update without a lock.
```python
# MISTAKE: Vulnerable to race conditions
merchant = Merchant.objects.get(id=merchant_id)
if merchant.cached_balance >= amount:
    # A second request executing right here sees the old balance before the save below!
    merchant.cached_balance -= amount
    merchant.save()
```

**Correction (Event Sourcing Ledger + Locks):**
```python
# CORRECT
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    # Re-calculate balance dynamically from ledger inside the lock window:
    balance = calculate_ledger_balance(merchant)
    if balance >= amount:
        Ledger.objects.create(merchant=merchant, amount=amount, entry_type='DEBIT')
```
