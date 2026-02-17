from django.db import models


class BaseModel(models.Model):
    """
    Abstract base model providing common timestamp fields.

    All concrete models in the wallets app should inherit from this
    to ensure consistent created_at / updated_at tracking.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]
