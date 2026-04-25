import uuid
from django.db import models
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce

class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.id})"

    def get_balance(self):
        # We compute the balance on the fly to avoid floating point issues and race conditions.
        # This will be used inside transactions for consistency.
        totals = Ledger.objects.filter(merchant=self).aggregate(
            credits=Coalesce(Sum('amount', filter=Q(entry_type='CREDIT')), 0),
            debits=Coalesce(Sum('amount', filter=Q(entry_type='DEBIT')), 0)
        )
        return totals['credits'] - totals['debits']

class Payout(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='payouts')
    amount = models.BigIntegerField()  # In Paise
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payout {self.id} for {self.merchant.name} - {self.amount} ({self.status})"

class Ledger(models.Model):
    ENTRY_CHOICES = (
        ('CREDIT', 'Credit'),  # Adds to balance
        ('DEBIT', 'Debit'),    # Subtracts from balance
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='ledger_entries')
    amount = models.BigIntegerField()
    entry_type = models.CharField(max_length=10, choices=ENTRY_CHOICES)
    purpose = models.CharField(max_length=255)
    payout_reference = models.ForeignKey(Payout, on_delete=models.SET_NULL, null=True, blank=True, related_name='ledger_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.entry_type} for {self.merchant.name} - {self.amount} paise ({self.purpose})"

class IdempotencyKey(models.Model):
    key = models.CharField(max_length=255, primary_key=True)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, null=True, blank=True)
    request_path = models.CharField(max_length=255)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    locked_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Idempotency {self.key}"
