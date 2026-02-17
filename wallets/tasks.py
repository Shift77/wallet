import logging

from celery import shared_task
from django.conf import settings

from wallets.models import Transaction
from wallets.services import WithdrawalService

logger = logging.getLogger(__name__)

MAX_RETRIES = getattr(settings, "WITHDRAWAL_MAX_RETRIES", 3)


@shared_task(bind=True, acks_late=True, max_retries=3, default_retry_delay=30)
def process_single_withdrawal(self, transaction_id: int):
    """
    Process a single withdrawal transaction.

    Uses acks_late=True so the task won't be acknowledged until it completes,
    preventing task loss if the worker crashes mid-processing.
    """
    try:
        logger.info("Processing withdrawal transaction_id=%d", transaction_id)
        tx = WithdrawalService.execute(transaction_id)

        if tx.status == Transaction.Status.COMPLETED:
            logger.info("Withdrawal tx=%d completed successfully.", transaction_id)
        else:
            logger.warning(
                "Withdrawal tx=%d failed: %s", transaction_id, tx.third_party_response
            )

        return {
            "transaction_id": transaction_id,
            "status": tx.status,
        }

    except Transaction.DoesNotExist:
        logger.error("Transaction %d not found or already processed.", transaction_id)
        return {"transaction_id": transaction_id, "status": "NOT_FOUND"}

    except Exception as exc:
        logger.exception(
            "Unexpected error processing withdrawal tx=%d: %s",
            transaction_id,
            str(exc),
        )
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2**self.request.retries * 10)


@shared_task
def process_pending_withdrawals():
    """
    Periodic task: Find all pending withdrawals whose scheduled time has arrived
    and dispatch each for individual processing.

    Runs via Celery Beat on a configurable interval.
    """
    pending_txs = Transaction.get_due_pending_withdrawals()
    count = pending_txs.count()

    if count == 0:
        return {"dispatched": 0}

    logger.info("Found %d pending withdrawal(s) due for processing.", count)

    for tx in pending_txs:
        process_single_withdrawal.delay(tx.id)

    return {"dispatched": count}


@shared_task
def retry_failed_withdrawals():
    """
    Periodic task: Find failed withdrawals eligible for retry and re-dispatch them.

    Transactions are retried up to MAX_RETRIES times.
    """
    failed_txs = Transaction.get_failed_retryable_withdrawals(max_retries=MAX_RETRIES)
    count = failed_txs.count()

    if count == 0:
        return {"dispatched": 0}

    logger.info("Found %d failed withdrawal(s) eligible for retry.", count)

    for tx in failed_txs:
        process_single_withdrawal.delay(tx.id)

    return {"dispatched": count}
