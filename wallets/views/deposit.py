import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from wallets.models import Wallet
from wallets.serializers import (
    DepositSerializer,
    TransactionSerializer,
    WalletSerializer,
)
from wallets.services import WalletService

logger = logging.getLogger(__name__)


class CreateDepositView(APIView):
    """
    POST /wallets/<uuid>/deposit — Deposit into a wallet.

    Request body: {"amount": <positive integer>}
    """

    def post(self, request, uuid, *args, **kwargs):
        serializer = DepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")

        try:
            tx = WalletService.deposit(
                wallet_uuid=uuid,
                amount=serializer.validated_data["amount"],
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
            {
                "wallet": WalletSerializer(tx.wallet).data,
                "transaction": TransactionSerializer(tx).data,
            },
            status=status.HTTP_200_OK,
        )
