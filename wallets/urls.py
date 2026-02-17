from django.urls import path

from wallets.views import (
    CreateDepositView,
    CreateWalletView,
    RetrieveWalletView,
    ScheduleWithdrawView,
    TransactionDetailView,
    TransactionListView,
)

urlpatterns = [
    path("", CreateWalletView.as_view(), name="wallet-create"),
    path("<uuid>/", RetrieveWalletView.as_view(), name="wallet-detail"),
    path("<uuid>/deposit", CreateDepositView.as_view(), name="wallet-deposit"),
    path("<uuid>/withdraw", ScheduleWithdrawView.as_view(), name="wallet-withdraw"),
    path(
        "<uuid>/transactions/",
        TransactionListView.as_view(),
        name="wallet-transactions",
    ),
    path(
        "<uuid>/transactions/<int:id>/",
        TransactionDetailView.as_view(),
        name="transaction-detail",
    ),
]
