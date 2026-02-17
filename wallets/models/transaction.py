from django.db import models
from django.utils import timezone

from wallets.models.base import BaseModel
from wallets.models.wallet import Wallet


class Transaction(BaseModel):
    """
    Records every wallet operation (deposit or withdrawal).

    Withdrawals are created with PENDING status and a future `scheduled_for` time.
    They are executed by the Celery task scheduler when the scheduled time arrives.
    The third-party bank response is stored for auditing and debugging.
    """

    class TransactionType(models.TextChoices):
        DEPOSIT = "DEPOSIT", "Deposit"
        WITHDRAWAL = "WITHDRAWAL", "Withdrawal"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    amount = models.BigIntegerField()
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The future time at which a withdrawal should be executed.",
    )
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the transaction was actually processed.",
    )
    third_party_response = models.JSONField(
        null=True,
        blank=True,
        help_text="Response from the third-party bank service.",
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this transaction has been retried.",
    )
    idempotency_key = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text="Client-generated UUID for idempotency.",
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["status", "scheduled_for"], name="idx_status_scheduled"
            ),
            models.Index(fields=["wallet", "status"], name="idx_wallet_status"),
        ]

    def __str__(self):
        return (
            f"Transaction {self.id} | {self.transaction_type} | "
            f"{self.amount} | {self.status}"
        )

    @classmethod
    def get_due_pending_withdrawals(cls):
        """Return withdrawals that are due for processing."""
        return cls.objects.filter(
            transaction_type=cls.TransactionType.WITHDRAWAL,
            status=cls.Status.PENDING,
            scheduled_for__lte=timezone.now(),
        )

    @classmethod
    def get_failed_retryable_withdrawals(cls, max_retries=3):
        """Return failed withdrawals eligible for retry."""
        return cls.objects.filter(
            transaction_type=cls.TransactionType.WITHDRAWAL,
            status=cls.Status.FAILED,
            retry_count__lt=max_retries,
        )
