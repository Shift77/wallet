from rest_framework import serializers


class DepositSerializer(serializers.Serializer):
    """Validates deposit requests."""

    amount = serializers.IntegerField(min_value=1)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be a positive integer.")
        return value
