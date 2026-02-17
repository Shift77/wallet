import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from wallets.models import Wallet
from wallets.serializers import ScheduleWithdrawSerializer, TransactionSerializer
from wallets.services import WithdrawalService

logger = logging.getLogger(__name__)


class ScheduleWithdrawView(APIView):
    """
    POST /wallets/<uuid>/withdraw — Schedule a future withdrawal.

    Request body: {"amount": <positive integer>, "scheduled_for": "<ISO datetime>"}
    Note: Balance is validated at execution time, not at scheduling time.
    """

    def post(self, request, uuid, *args, **kwargs):
        serializer = ScheduleWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")

        try:
            tx = WithdrawalService.schedule(
                wallet_uuid=uuid,
                amount=serializer.validated_data["amount"],
                scheduled_for=serializer.validated_data["scheduled_for"],
                idempotency_key=idempotency_key,
            )
        except Wallet.DoesNotExist:
            return Response(
                {"error": "Wallet not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            TransactionSerializer(tx).data,
            status=status.HTTP_201_CREATED,
        )
