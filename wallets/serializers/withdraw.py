from django.utils import timezone
from rest_framework import serializers


class ScheduleWithdrawSerializer(serializers.Serializer):
    """Validates withdrawal scheduling requests."""

    amount = serializers.IntegerField(min_value=1)
    scheduled_for = serializers.DateTimeField()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be a positive integer.")
        return value

    def validate_scheduled_for(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future.")
        return value
