import uuid

from django.db import models

from wallets.models.base import BaseModel


class Wallet(BaseModel):
    """
    Represents a user's wallet with a non-negative balance.

    Uses BigIntegerField for balance to handle large amounts (stored in smallest
    currency unit, e.g. Rials). Concurrency safety is handled at the service layer
    via select_for_update() and F() expressions.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )
    balance = models.BigIntegerField(default=0)

    def __str__(self):
        return f"Wallet {self.uuid} (balance={self.balance})"
