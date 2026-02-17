import logging

from rest_framework.generics import ListAPIView, RetrieveAPIView

from wallets.models import Transaction
from wallets.serializers import TransactionSerializer

logger = logging.getLogger(__name__)


class TransactionListView(ListAPIView):
    """
    GET /wallets/<uuid>/transactions/ — List all transactions for a wallet.

    Query params:
        - status: Filter by transaction status (PENDING, PROCESSING, COMPLETED, FAILED)
        - type: Filter by transaction type (DEPOSIT, WITHDRAWAL)
    """

    serializer_class = TransactionSerializer

    def get_queryset(self):
        wallet_uuid = self.kwargs["uuid"]
        queryset = Transaction.objects.filter(wallet__uuid=wallet_uuid)

        # Optional filters
        tx_status = self.request.query_params.get("status")
        if tx_status:
            queryset = queryset.filter(status=tx_status.upper())

        tx_type = self.request.query_params.get("type")
        if tx_type:
            queryset = queryset.filter(transaction_type=tx_type.upper())

        return queryset


class TransactionDetailView(RetrieveAPIView):
    """GET /wallets/<uuid>/transactions/<id>/ — Retrieve a single transaction."""

    serializer_class = TransactionSerializer
    lookup_field = "id"

    def get_queryset(self):
        wallet_uuid = self.kwargs["uuid"]
        return Transaction.objects.filter(wallet__uuid=wallet_uuid)
