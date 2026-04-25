from django.db import transaction
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ObjectDoesNotExist
from .models import Merchant, Payout, Ledger

VALID_TRANSITIONS = {
    'PENDING': ['PROCESSING', 'FAILED'],
    'PROCESSING': ['COMPLETED', 'FAILED'],
    'COMPLETED': [],
    'FAILED': []
}

def transition_payout_status(payout, new_status):
    """
    Enforce state machine rules for payouts.
    """
    if new_status not in VALID_TRANSITIONS.get(payout.status, []):
        raise ValueError(f"Invalid state transition from {payout.status} to {new_status}")
    payout.status = new_status
    payout.save(update_fields=['status', 'updated_at'])

def initiate_payout(merchant_id, amount):
    """
    Creates a payout request atomically, verifying the balance.
    Locks the merchant row to avoid race conditions and double spending.
    """
    with transaction.atomic():
        try:
            # We acquire a lock on this specific merchant
            merchant = Merchant.objects.select_for_update().get(id=merchant_id)
        except Merchant.DoesNotExist:
            raise ValidationError({"merchant": ["Merchant does not exist."]})
        
        # Calculate balance consistently from ledger
        balance = merchant.get_balance()
        if balance < amount:
            raise ValidationError({"amount": ["Insufficient balance."]})
        
        # Create PENDING payout
        payout = Payout.objects.create(
            merchant=merchant,
            amount=amount,
            status='PENDING'
        )
        
        # Immediately hold funds via Ledger DEBIT
        Ledger.objects.create(
            merchant=merchant,
            amount=amount,
            entry_type='DEBIT',
            purpose='PAYOUT_HOLD',
            payout_reference=payout
        )
        
        return payout

def refund_payout(payout):
    """
    Called when a payout definitively fails. Returns funds to merchant.
    """
    with transaction.atomic():
        # Lock merchant again to ensure ledger is consistently appended (though inserts usually don't strictly need locks, good for ordering tracking)
        merchant = Merchant.objects.select_for_update().get(id=payout.merchant_id)
        
        # We ensure it wasn't already refunded by checking ledger
        from django.db.models import Exists, OuterRef
        already_refunded = Ledger.objects.filter(
            merchant=merchant, 
            payout_reference=payout, 
            purpose='PAYOUT_REFUND'
        ).exists()
        
        if not already_refunded:
            Ledger.objects.create(
                merchant=merchant,
                amount=payout.amount,
                entry_type='CREDIT',
                purpose='PAYOUT_REFUND',
                payout_reference=payout
            )
