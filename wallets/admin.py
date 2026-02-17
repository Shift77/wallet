from django.contrib import admin

from wallets.models import Transaction, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("id", "uuid", "balance", "created_at", "updated_at")
    search_fields = ("uuid",)
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "wallet",
        "transaction_type",
        "amount",
        "status",
        "scheduled_for",
        "executed_at",
        "retry_count",
        "created_at",
    )
    list_filter = ("transaction_type", "status")
    search_fields = ("wallet__uuid",)
    readonly_fields = ("created_at", "updated_at", "third_party_response")
