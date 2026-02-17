import logging

from rest_framework.generics import CreateAPIView, RetrieveAPIView

from wallets.models import Wallet
from wallets.serializers import WalletSerializer

logger = logging.getLogger(__name__)


class CreateWalletView(CreateAPIView):
    """POST /wallets/ — Create a new wallet."""

    serializer_class = WalletSerializer


class RetrieveWalletView(RetrieveAPIView):
    """GET /wallets/<uuid>/ — Retrieve wallet details."""

    serializer_class = WalletSerializer
    queryset = Wallet.objects.all()
    lookup_field = "uuid"
