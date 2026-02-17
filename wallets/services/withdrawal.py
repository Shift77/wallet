import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from wallets.models import Transaction, Wallet
from wallets.utils import request_third_party_deposit

logger = logging.getLogger(__name__)


class WithdrawalService:
    """
    Handles withdrawal scheduling and execution.

    Scheduling: Creates a PENDING transaction with a future execution time.
    Execution: At the scheduled time, acquires a lock on the wallet, validates
    the balance, deducts the amount, and calls the third-party bank service.
    If the third-party call fails, the amount is returned to the wallet.
    """

    @staticmethod
    @transaction.atomic
    def schedule(
        wallet_uuid: str, amount: int, scheduled_for, idempotency_key: str = None
    ) -> Transaction:
        """
        Schedule a withdrawal for a future time.

        Balance is NOT validated at scheduling time (per task requirements).
        Validation happens at execution time.

        Args:
            wallet_uuid: UUID of the target wallet.
            amount: Positive integer amount to withdraw.
            scheduled_for: Future datetime when the withdrawal should execute.
            idempotency_key: Optional UUID key for idempotency.

        Returns:
            The created (or existing) PENDING Transaction.

        Raises:
            Wallet.DoesNotExist: If wallet doesn't exist.
            ValueError: If amount is not positive or scheduled_for is not in the future.
        """
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive.")

        if scheduled_for <= timezone.now():
            raise ValueError("Scheduled time must be in the future.")

        # Check for existing idempotent transaction
        if idempotency_key:
            existing_tx = Transaction.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing_tx:
                if existing_tx.amount != amount or str(existing_tx.wallet.uuid) != str(
                    wallet_uuid
                ):
                    logger.warning(
                        "Idempotency conflict: key=%s existing_amount=%d new_amount=%d",
                        idempotency_key,
                        existing_tx.amount,
                        amount,
                    )
                    pass

                logger.info(
                    "Idempotent withdrawal request: key=%s tx=%d",
                    idempotency_key,
                    existing_tx.id,
                )
                return existing_tx

        wallet = Wallet.objects.get(uuid=wallet_uuid)

        tx = Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.PENDING,
            scheduled_for=scheduled_for,
            idempotency_key=idempotency_key,
        )

        logger.info(
            "Withdrawal scheduled: wallet=%s amount=%d scheduled_for=%s tx=%d idempotency_key=%s",
            wallet_uuid,
            amount,
            scheduled_for,
            tx.id,
            idempotency_key,
        )
        return tx

    @staticmethod
    @transaction.atomic
    def execute(transaction_id: int) -> Transaction:
        """
        Execute a pending withdrawal transaction.

        This method:
        1. Locks the transaction row to prevent double-processing.
        2. Locks the wallet row to prevent concurrent balance modifications.
        3. Validates the wallet has sufficient balance.
        4. Deducts the amount from the wallet.
        5. Calls the third-party bank service.
        6. If the bank call fails, rolls back the balance deduction.

        Args:
            transaction_id: ID of the pending transaction to execute.

        Returns:
            The updated Transaction (COMPLETED or FAILED).

        Raises:
            Transaction.DoesNotExist: If transaction doesn't exist.
        """
        # Lock the transaction to prevent double-processing
        tx = Transaction.objects.select_for_update().get(
            id=transaction_id,
            status__in=[Transaction.Status.PENDING, Transaction.Status.FAILED],
        )

        # Mark as processing
        tx.status = Transaction.Status.PROCESSING
        tx.save(update_fields=["status", "updated_at"])

        # Lock the wallet
        wallet = Wallet.objects.select_for_update().get(pk=tx.wallet_id)

        # Validate balance at execution time
        if wallet.balance < tx.amount:
            tx.status = Transaction.Status.FAILED
            tx.executed_at = timezone.now()
            tx.third_party_response = {"error": "Insufficient balance"}
            tx.save(
                update_fields=[
                    "status",
                    "executed_at",
                    "third_party_response",
                    "updated_at",
                ]
            )

            logger.warning(
                "Withdrawal failed (insufficient balance): wallet=%s balance=%d "
                "amount=%d tx=%d",
                wallet.uuid,
                wallet.balance,
                tx.amount,
                tx.id,
            )
            return tx

        # Deduct balance atomically
        Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") - tx.amount)

        # Call third-party bank service
        third_party_result = request_third_party_deposit(
            wallet_uuid=str(wallet.uuid),
            amount=tx.amount,
        )

        if third_party_result["success"]:
            tx.status = Transaction.Status.COMPLETED
            tx.executed_at = timezone.now()
            tx.third_party_response = third_party_result["response"]
            tx.save(
                update_fields=[
                    "status",
                    "executed_at",
                    "third_party_response",
                    "updated_at",
                ]
            )

            logger.info(
                "Withdrawal completed: wallet=%s amount=%d tx=%d",
                wallet.uuid,
                tx.amount,
                tx.id,
            )
        else:
            # Third-party failed — return the amount to the wallet
            Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") + tx.amount)

            tx.status = Transaction.Status.FAILED
            tx.executed_at = timezone.now()
            tx.retry_count = F("retry_count") + 1
            tx.third_party_response = third_party_result["response"]
            tx.save(
                update_fields=[
                    "status",
                    "executed_at",
                    "retry_count",
                    "third_party_response",
                    "updated_at",
                ]
            )
            tx.refresh_from_db()

            logger.warning(
                "Withdrawal failed (third-party error): wallet=%s amount=%d "
                "tx=%d retry_count=%d response=%s",
                wallet.uuid,
                tx.amount,
                tx.id,
                tx.retry_count,
                third_party_result["response"],
            )

        return tx
