import random
import time
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from .models import Payout
from .services import transition_payout_status, refund_payout

def process_payout_task(payout_id):
    """
    Simulates sending payout to bank wrapper/gateway.
    70% success, 20% fail, 10% stuck (sleep + Exception -> triggers retry)
    """
    try:
        payout = Payout.objects.get(id=payout_id)
    except Payout.DoesNotExist:
        return
        
    if payout.status not in ['PENDING', 'PROCESSING']:
        return # Already handled
        
    # Mark as processing
    if payout.status == 'PENDING':
        transition_payout_status(payout, 'PROCESSING')
        
    outcome = random.random()
    
    if outcome < 0.70:
        # Success
        transition_payout_status(payout, 'COMPLETED')
        return "SUCCESS"
        
    elif outcome < 0.90:
        # Fail
        transition_payout_status(payout, 'FAILED')
        refund_payout(payout)
        return "FAILED"
        
    else:
        # Stuck - simulate timeout and raise exception to trigger retry
        payout.attempts += 1
        payout.save(update_fields=['attempts', 'updated_at'])
        
        # We raise exception, which triggers django-q retry mechanism
        # or the periodic task will pick it up
        raise Exception("Payout processing timeout, triggering retry.")

def cleanup_stuck_payouts():
    """
    Periodic task that finds payouts stuck in PROCESSING for > 30 seconds.
    Retries them or fails and refunds if they exceed max attempts.
    """
    threshold_time = timezone.now() - timedelta(seconds=30)
    
    stuck_payouts = Payout.objects.filter(
        status='PROCESSING',
        updated_at__lt=threshold_time
    )
    
    for payout in stuck_payouts:
        # We lock specific row
        with transaction.atomic():
            locked_payout = Payout.objects.select_for_update().get(id=payout.id)
            if locked_payout.status != 'PROCESSING':
                continue # Edge case: handled in between select and lock
                
            if locked_payout.attempts >= 3:
                # Max retries exceeded
                transition_payout_status(locked_payout, 'FAILED')
                refund_payout(locked_payout)
            else:
                # Increment attempts and re-queue
                locked_payout.attempts += 1
                locked_payout.save(update_fields=['attempts'])
                # exponential backoff delay manually if needed, but dispatching now
                from django_q.tasks import async_task
                async_task('api.tasks.process_payout_task', str(locked_payout.id))
