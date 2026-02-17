from rest_framework import serializers

from wallets.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    """Read-only serializer for transaction responses."""

    wallet_uuid = serializers.UUIDField(source="wallet.uuid", read_only=True)

    class Meta:
        model = Transaction
        fields = (
            "id",
            "wallet_uuid",
            "amount",
            "transaction_type",
            "status",
            "scheduled_for",
            "executed_at",
            "third_party_response",
            "retry_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
