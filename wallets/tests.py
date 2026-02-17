import json
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from wallets.models import Transaction, Wallet
from wallets.services import WalletService, WithdrawalService

# ============================================================
# Model Tests
# ============================================================


class WalletModelTest(TestCase):
    def test_create_wallet(self):
        wallet = Wallet.objects.create()
        self.assertIsNotNone(wallet.uuid)
        self.assertEqual(wallet.balance, 0)
        self.assertIsNotNone(wallet.created_at)

    def test_wallet_str(self):
        wallet = Wallet.objects.create()
        self.assertIn(str(wallet.uuid), str(wallet))

    def test_wallet_uuid_is_unique(self):
        w1 = Wallet.objects.create()
        w2 = Wallet.objects.create()
        self.assertNotEqual(w1.uuid, w2.uuid)


class TransactionModelTest(TestCase):
    def setUp(self):
        self.wallet = Wallet.objects.create()

    def test_create_deposit_transaction(self):
        tx = Transaction.objects.create(
            wallet=self.wallet,
            amount=1000,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            status=Transaction.Status.COMPLETED,
        )
        self.assertEqual(tx.transaction_type, "DEPOSIT")
        self.assertEqual(tx.status, "COMPLETED")
        self.assertEqual(tx.amount, 1000)

    def test_create_withdrawal_transaction(self):
        future = timezone.now() + timedelta(minutes=10)
        tx = Transaction.objects.create(
            wallet=self.wallet,
            amount=500,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.PENDING,
            scheduled_for=future,
        )
        self.assertEqual(tx.status, "PENDING")
        self.assertIsNotNone(tx.scheduled_for)

    def test_get_due_pending_withdrawals(self):
        past = timezone.now() - timedelta(minutes=5)
        future = timezone.now() + timedelta(minutes=10)

        # Due withdrawal (scheduled_for in the past)
        tx_due = Transaction.objects.create(
            wallet=self.wallet,
            amount=100,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.PENDING,
            scheduled_for=past,
        )
        # Future withdrawal (not yet due)
        Transaction.objects.create(
            wallet=self.wallet,
            amount=200,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.PENDING,
            scheduled_for=future,
        )

        due = Transaction.get_due_pending_withdrawals()
        self.assertEqual(due.count(), 1)
        self.assertEqual(due.first().id, tx_due.id)

    def test_get_failed_retryable_withdrawals(self):
        tx_retryable = Transaction.objects.create(
            wallet=self.wallet,
            amount=100,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.FAILED,
            retry_count=1,
        )
        # Exhausted retries
        Transaction.objects.create(
            wallet=self.wallet,
            amount=200,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.FAILED,
            retry_count=3,
        )

        retryable = Transaction.get_failed_retryable_withdrawals(max_retries=3)
        self.assertEqual(retryable.count(), 1)
        self.assertEqual(retryable.first().id, tx_retryable.id)

    def test_transaction_str(self):
        tx = Transaction.objects.create(
            wallet=self.wallet,
            amount=500,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            status=Transaction.Status.COMPLETED,
        )
        self.assertIn("DEPOSIT", str(tx))
        self.assertIn("500", str(tx))


# ============================================================
# Service Tests
# ============================================================


class WalletServiceTest(TransactionTestCase):
    def setUp(self):
        self.wallet = Wallet.objects.create()

    def test_deposit_success(self):
        tx = WalletService.deposit(self.wallet.uuid, 1000)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1000)
        self.assertEqual(tx.status, Transaction.Status.COMPLETED)
        self.assertEqual(tx.transaction_type, Transaction.TransactionType.DEPOSIT)
        self.assertEqual(tx.amount, 1000)
        self.assertIsNotNone(tx.executed_at)

    def test_deposit_multiple(self):
        WalletService.deposit(self.wallet.uuid, 1000)
        WalletService.deposit(self.wallet.uuid, 2500)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 3500)

    def test_deposit_zero_amount_raises(self):
        with self.assertRaises(ValueError):
            WalletService.deposit(self.wallet.uuid, 0)

    def test_deposit_negative_amount_raises(self):
        with self.assertRaises(ValueError):
            WalletService.deposit(self.wallet.uuid, -100)

    def test_deposit_nonexistent_wallet_raises(self):
        import uuid

        with self.assertRaises(Wallet.DoesNotExist):
            WalletService.deposit(uuid.uuid4(), 1000)

    def test_deposit_idempotency(self):
        import uuid

        key = str(uuid.uuid4())

        # First deposit
        tx1 = WalletService.deposit(self.wallet.uuid, 1000, idempotency_key=key)
        self.assertEqual(tx1.amount, 1000)
        self.assertEqual(str(tx1.idempotency_key), key)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1000)

        # Duplicate deposit
        tx2 = WalletService.deposit(self.wallet.uuid, 1000, idempotency_key=key)

        # Should return same transaction
        self.assertEqual(tx1.id, tx2.id)

        # Balance should NOT increase
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1000)


class WithdrawalServiceTest(TransactionTestCase):
    def setUp(self):
        self.wallet = Wallet.objects.create()
        WalletService.deposit(self.wallet.uuid, 10000)
        self.wallet.refresh_from_db()

    def test_schedule_success(self):
        future = timezone.now() + timedelta(minutes=30)
        tx = WithdrawalService.schedule(self.wallet.uuid, 5000, future)

        self.assertEqual(tx.status, Transaction.Status.PENDING)
        self.assertEqual(tx.amount, 5000)
        self.assertEqual(tx.scheduled_for, future)
        # Balance should NOT change at scheduling time
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 10000)

    def test_schedule_past_time_raises(self):
        past = timezone.now() - timedelta(minutes=5)
        with self.assertRaises(ValueError):
            WithdrawalService.schedule(self.wallet.uuid, 5000, past)

    def test_schedule_zero_amount_raises(self):
        future = timezone.now() + timedelta(minutes=30)
        with self.assertRaises(ValueError):
            WithdrawalService.schedule(self.wallet.uuid, 0, future)

    def test_schedule_idempotency(self):
        import uuid

        future = timezone.now() + timedelta(minutes=30)
        key = str(uuid.uuid4())

        tx1 = WithdrawalService.schedule(
            self.wallet.uuid, 5000, future, idempotency_key=key
        )
        self.assertEqual(str(tx1.idempotency_key), key)
        self.assertEqual(tx1.status, Transaction.Status.PENDING)

        tx2 = WithdrawalService.schedule(
            self.wallet.uuid, 5000, future, idempotency_key=key
        )

        self.assertEqual(tx1.id, tx2.id)

    @patch("wallets.services.withdrawal.request_third_party_deposit")
    def test_execute_success(self, mock_third_party):
        mock_third_party.return_value = {
            "success": True,
            "response": {"data": "success", "status": 200},
        }

        future = timezone.now() + timedelta(minutes=30)
        tx = WithdrawalService.schedule(self.wallet.uuid, 3000, future)

        # Execute the withdrawal
        result = WithdrawalService.execute(tx.id)

        self.assertEqual(result.status, Transaction.Status.COMPLETED)
        self.assertIsNotNone(result.executed_at)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 7000)  # 10000 - 3000

        mock_third_party.assert_called_once_with(
            wallet_uuid=str(self.wallet.uuid),
            amount=3000,
        )

    @patch("wallets.services.withdrawal.request_third_party_deposit")
    def test_execute_insufficient_balance(self, mock_third_party):
        future = timezone.now() + timedelta(minutes=30)
        tx = WithdrawalService.schedule(self.wallet.uuid, 50000, future)

        result = WithdrawalService.execute(tx.id)

        self.assertEqual(result.status, Transaction.Status.FAILED)
        self.assertIn("Insufficient balance", str(result.third_party_response))

        # Balance should NOT change
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 10000)

        # Third-party should NOT be called
        mock_third_party.assert_not_called()

    @patch("wallets.services.withdrawal.request_third_party_deposit")
    def test_execute_third_party_failure_refunds(self, mock_third_party):
        mock_third_party.return_value = {
            "success": False,
            "response": {"data": "failed", "status": 503},
        }

        future = timezone.now() + timedelta(minutes=30)
        tx = WithdrawalService.schedule(self.wallet.uuid, 3000, future)

        result = WithdrawalService.execute(tx.id)

        self.assertEqual(result.status, Transaction.Status.FAILED)

        # Balance should be refunded
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 10000)

        # Retry count should increment
        self.assertEqual(result.retry_count, 1)

    @patch("wallets.services.withdrawal.request_third_party_deposit")
    def test_execute_already_processed_raises(self, mock_third_party):
        mock_third_party.return_value = {
            "success": True,
            "response": {"data": "success", "status": 200},
        }

        future = timezone.now() + timedelta(minutes=30)
        tx = WithdrawalService.schedule(self.wallet.uuid, 3000, future)
        WithdrawalService.execute(tx.id)

        # Trying to execute again should raise (status is now COMPLETED)
        with self.assertRaises(Transaction.DoesNotExist):
            WithdrawalService.execute(tx.id)


# ============================================================
# API Tests
# ============================================================


class WalletAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_create_wallet(self):
        response = self.client.post("/wallets/", format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("uuid", response.data)
        self.assertEqual(response.data["balance"], 0)

    def test_retrieve_wallet(self):
        wallet = Wallet.objects.create()
        response = self.client.get(f"/wallets/{wallet.uuid}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["uuid"], str(wallet.uuid))

    def test_retrieve_nonexistent_wallet(self):
        import uuid

        response = self.client.get(f"/wallets/{uuid.uuid4()}/")
        self.assertEqual(response.status_code, 404)


class DepositAPITest(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.wallet = Wallet.objects.create()

    def test_deposit_success(self):
        response = self.client.post(
            f"/wallets/{self.wallet.uuid}/deposit",
            {"amount": 5000},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["wallet"]["balance"], 5000)
        self.assertEqual(response.data["transaction"]["amount"], 5000)
        self.assertEqual(response.data["transaction"]["status"], "COMPLETED")

    def test_deposit_with_idempotency_key(self):
        import uuid

        key = str(uuid.uuid4())
        response1 = self.client.post(
            f"/wallets/{self.wallet.uuid}/deposit",
            {"amount": 5000},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(response1.status_code, 200)

        response2 = self.client.post(
            f"/wallets/{self.wallet.uuid}/deposit",
            {"amount": 5000},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(
            response1.data["transaction"]["id"], response2.data["transaction"]["id"]
        )

    def test_deposit_zero_amount(self):
        response = self.client.post(
            f"/wallets/{self.wallet.uuid}/deposit",
            {"amount": 0},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_deposit_negative_amount(self):
        response = self.client.post(
            f"/wallets/{self.wallet.uuid}/deposit",
            {"amount": -1000},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_deposit_missing_amount(self):
        response = self.client.post(
            f"/wallets/{self.wallet.uuid}/deposit",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_deposit_nonexistent_wallet(self):
        import uuid

        response = self.client.post(
            f"/wallets/{uuid.uuid4()}/deposit",
            {"amount": 1000},
            format="json",
        )
        self.assertEqual(response.status_code, 404)


class WithdrawAPITest(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.wallet = Wallet.objects.create()
        WalletService.deposit(self.wallet.uuid, 10000)
        self.wallet.refresh_from_db()

    def test_schedule_withdraw_success(self):
        future = (timezone.now() + timedelta(minutes=30)).isoformat()
        response = self.client.post(
            f"/wallets/{self.wallet.uuid}/withdraw",
            {"amount": 3000, "scheduled_for": future},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["amount"], 3000)

        # Balance should NOT change at scheduling time
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 10000)

    def test_schedule_withdraw_with_idempotency_key(self):
        import uuid

        future = (timezone.now() + timedelta(minutes=30)).isoformat()
        key = str(uuid.uuid4())

        response1 = self.client.post(
            f"/wallets/{self.wallet.uuid}/withdraw",
            {"amount": 3000, "scheduled_for": future},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(response1.status_code, 201)

        response2 = self.client.post(
            f"/wallets/{self.wallet.uuid}/withdraw",
            {"amount": 3000, "scheduled_for": future},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(response2.status_code, 201)
        self.assertEqual(response1.data["id"], response2.data["id"])

    def test_schedule_withdraw_past_time(self):
        past = (timezone.now() - timedelta(minutes=5)).isoformat()
        response = self.client.post(
            f"/wallets/{self.wallet.uuid}/withdraw",
            {"amount": 3000, "scheduled_for": past},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_schedule_withdraw_zero_amount(self):
        future = (timezone.now() + timedelta(minutes=30)).isoformat()
        response = self.client.post(
            f"/wallets/{self.wallet.uuid}/withdraw",
            {"amount": 0, "scheduled_for": future},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_schedule_withdraw_missing_scheduled_for(self):
        response = self.client.post(
            f"/wallets/{self.wallet.uuid}/withdraw",
            {"amount": 3000},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_schedule_withdraw_nonexistent_wallet(self):
        import uuid

        future = (timezone.now() + timedelta(minutes=30)).isoformat()
        response = self.client.post(
            f"/wallets/{uuid.uuid4()}/withdraw",
            {"amount": 3000, "scheduled_for": future},
            format="json",
        )
        self.assertEqual(response.status_code, 404)


class TransactionAPITest(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.wallet = Wallet.objects.create()
        WalletService.deposit(self.wallet.uuid, 10000)
        WalletService.deposit(self.wallet.uuid, 5000)
        future = timezone.now() + timedelta(minutes=30)
        WithdrawalService.schedule(self.wallet.uuid, 3000, future)

    def test_list_transactions(self):
        response = self.client.get(f"/wallets/{self.wallet.uuid}/transactions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)  # 2 deposits + 1 withdrawal

    def test_filter_by_status(self):
        response = self.client.get(
            f"/wallets/{self.wallet.uuid}/transactions/?status=PENDING"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_filter_by_type(self):
        response = self.client.get(
            f"/wallets/{self.wallet.uuid}/transactions/?type=DEPOSIT"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_transaction_detail(self):
        tx = Transaction.objects.filter(wallet=self.wallet).first()
        response = self.client.get(f"/wallets/{self.wallet.uuid}/transactions/{tx.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], tx.id)


# ============================================================
# Celery Task Tests (with mocked services)
# ============================================================


class CeleryTaskTest(TransactionTestCase):
    def setUp(self):
        self.wallet = Wallet.objects.create()
        WalletService.deposit(self.wallet.uuid, 10000)

    @patch("wallets.services.withdrawal.request_third_party_deposit")
    def test_process_pending_withdrawals(self, mock_third_party):
        mock_third_party.return_value = {
            "success": True,
            "response": {"data": "success", "status": 200},
        }

        # Create a withdrawal that is already due
        past = timezone.now() - timedelta(minutes=1)
        tx = Transaction.objects.create(
            wallet=self.wallet,
            amount=2000,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.PENDING,
            scheduled_for=past,
        )

        from wallets.tasks import process_pending_withdrawals, process_single_withdrawal

        # Use .apply() to run synchronously in tests
        result = process_pending_withdrawals.apply()
        self.assertEqual(result.get()["dispatched"], 1)

    @patch("wallets.services.withdrawal.request_third_party_deposit")
    def test_process_single_withdrawal_task(self, mock_third_party):
        mock_third_party.return_value = {
            "success": True,
            "response": {"data": "success", "status": 200},
        }

        future = timezone.now() + timedelta(minutes=30)
        tx = WithdrawalService.schedule(self.wallet.uuid, 2000, future)

        from wallets.tasks import process_single_withdrawal

        result = process_single_withdrawal.apply(args=[tx.id])

        self.assertEqual(result.get()["status"], Transaction.Status.COMPLETED)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 8000)

    @patch("wallets.utils.request_third_party_deposit")
    def test_retry_failed_withdrawals(self, mock_third_party):
        mock_third_party.return_value = {
            "success": False,
            "response": {"data": "failed", "status": 503},
        }

        # Create a failed withdrawal eligible for retry
        tx = Transaction.objects.create(
            wallet=self.wallet,
            amount=2000,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.FAILED,
            retry_count=1,
        )

        from wallets.tasks import retry_failed_withdrawals

        result = retry_failed_withdrawals.apply()
        self.assertEqual(result.get()["dispatched"], 1)
