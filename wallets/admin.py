from django.contrib import admin

from wallets.models import Transaction, Wallet


class ReadOnlyAdminMixin:
    """
    Mixin that makes an admin model completely read-only.
    Disables add, change, and delete permissions while keeping
    the model visible and browsable in the admin panel.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Wallet)
class WalletAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("id", "uuid", "balance", "created_at", "updated_at")
    search_fields = ("uuid",)
    readonly_fields = ("uuid", "balance", "created_at", "updated_at")


@admin.register(Transaction)
class TransactionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
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
    readonly_fields = (
        "wallet",
        "amount",
        "transaction_type",
        "status",
        "scheduled_for",
        "executed_at",
        "third_party_response",
        "retry_count",
        "idempotency_key",
        "created_at",
        "updated_at",
    )
