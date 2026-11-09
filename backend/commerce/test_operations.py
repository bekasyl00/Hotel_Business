import io
import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from psycopg.types.range import Range

from booking.models import Booking

from .jobs import claim, finish, run_one
from .models import OperationalHeartbeat, PaymentAttempt, PaymentJob, RefundRequest, WebhookDelivery
from .operations import finish_heartbeat, operations_snapshot, prometheus_samples, start_heartbeat
from .providers.base import ProviderError
from .scheduler import tick
from .tests import fixture


class OperationsTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.resort, self.booking, self.manager = fixture()
        self.index = 0

    def payment(self, *, provider="xpayment", environment="production", status="pending"):
        self.index += 1
        start = timezone.localdate() + timedelta(days=10 * self.index)
        booking = Booking.objects.create(
            resort=self.resort,
            room=self.booking.room,
            stay=Range(start, start + timedelta(days=1)),
            guests=1,
            guest_label="PRIVATE-NAME",
            guest_phone="PRIVATE-PHONE",
            owner="PRIVATE-OWNER",
            source="website",
            status="pending",
            hold_expires_at=self.now + timedelta(minutes=15),
            request_key=uuid4(),
            request_hash="fixture",
            snapshot={"total": 100},
        )
        payment = PaymentAttempt.objects.create(
            booking=booking,
            provider=provider,
            environment=environment,
            merchant_scope="PRIVATE-MERCHANT",
            request_key=uuid4(),
            fingerprint="PRIVATE-FINGERPRINT",
            actor_binding="PRIVATE-ACTOR",
            invoice_id=str(uuid4()),
            amount=100,
            status=status,
            expires_at=self.now + timedelta(minutes=15),
        )
        PaymentAttempt.objects.filter(pk=payment.pk).update(
            created_at=self.now - timedelta(minutes=5)
        )
        return payment

    def test_empty_snapshot_is_six_queries_and_missing_worker_is_not_healthy(self):
        with self.assertNumQueries(6):
            snapshot = operations_snapshot(now=self.now)
        self.assertEqual(snapshot["jobs"], [])
        self.assertEqual(snapshot["holds"]["overdue"], 0)
        self.assertTrue(all(row["status"] == "missing" for row in snapshot["heartbeats"]))
        metrics = {name: rows for name, _, rows in prometheus_samples(snapshot)}
        self.assertEqual(len(metrics["tynys_payment_jobs"]), 45)
        self.assertTrue(all(value == 0 for _, value in metrics["tynys_payment_jobs"]))
        self.assertEqual(
            metrics["tynys_worker_heartbeat_present"],
            [
                ({"worker": "payment_scheduler"}, 0),
                ({"worker": "payment_worker"}, 0),
            ],
        )
        self.assertEqual(OperationalHeartbeat.objects.count(), 0)

    def test_queue_deadlines_and_unknown_labels_do_not_leak_or_mutate_jobs(self):
        payment = self.payment()
        data = [
            ("create", "pending", -30, None),
            ("verify", "pending", 30, None),
            ("refund", "running", -60, self.now - timedelta(seconds=10)),
            ("refund_verify", "running", -60, None),
            ("deactivate", "done", -60, None),
        ]
        for kind, state, available, lease in data:
            PaymentJob.objects.create(
                payment=payment,
                kind=kind,
                state=state,
                available_at=self.now + timedelta(seconds=available),
                lease_until=lease,
            )
        PaymentJob.objects.create(
            payment=payment,
            kind="PRIVATE-KIND",
            state="PRIVATE",
            available_at=self.now,
            last_error="PRIVATE-ERROR",
        )
        before = list(PaymentJob.objects.values())
        snapshot = operations_snapshot(now=self.now)
        rows = {row["kind"]: row for row in snapshot["jobs"]}
        self.assertNotIn("deactivate", rows)
        self.assertEqual(rows["create"]["due"], 1)
        self.assertEqual(rows["create"]["oldest_due_seconds"], 30)
        self.assertEqual(rows["verify"]["due"], 0)
        self.assertEqual(rows["refund"]["expired_leases"], 1)
        self.assertEqual(rows["refund"]["oldest_expired_lease_seconds"], 10)
        self.assertEqual(rows["refund_verify"]["invalid_leases"], 1)
        self.assertEqual(rows["other"]["state"], "other")
        self.assertEqual(list(PaymentJob.objects.values()), before)
        self.assertNotIn("PRIVATE", json.dumps(snapshot))
        self.assertNotIn("PRIVATE", json.dumps(list(prometheus_samples(snapshot))))

    def test_scope_and_active_statuses_exclude_terminal_history(self):
        production = self.payment()
        sandbox = self.payment(environment="sandbox", status="reconciliation_required")
        settled = self.payment(status="succeeded")
        RefundRequest.objects.create(
            payment=production, amount=70, percent=70, status="queued", actor_kind="guest"
        )
        RefundRequest.objects.create(
            payment=settled, amount=70, percent=70, status="succeeded", actor_kind="guest"
        )
        old = WebhookDelivery.objects.create(
            payment=production,
            merchant_scope="PRIVATE-MERCHANT",
            delivery_id=uuid4(),
            event="payment.completed",
        )
        WebhookDelivery.objects.filter(pk=old.pk).update(received_at=self.now - timedelta(hours=2))
        WebhookDelivery.objects.create(
            payment=sandbox,
            merchant_scope="PRIVATE-MERCHANT",
            delivery_id=uuid4(),
            event="payment.completed",
        )
        snapshot = operations_snapshot(now=self.now)
        self.assertEqual(sum(row["count"] for row in snapshot["payments"]), 2)
        self.assertEqual(
            {row["environment"] for row in snapshot["payments"]}, {"production", "sandbox"}
        )
        self.assertTrue(all(row["oldest_seconds"] == 300 for row in snapshot["payments"]))
        self.assertEqual(snapshot["refunds"][0]["status"], "queued")
        self.assertEqual(len(snapshot["refunds"]), 1)
        self.assertEqual(snapshot["webhooks"][0]["environment"], "sandbox")
        self.assertEqual(snapshot["webhooks"][0]["received_last_hour"], 1)

    def test_overdue_and_legacy_holds_are_separate_and_not_expired_by_metrics(self):
        p = self.payment()
        Booking.objects.filter(pk=p.booking_id).update(
            hold_expires_at=self.now - timedelta(minutes=2)
        )
        self.booking.status, self.booking.hold_expires_at = "pending", None
        self.booking.save(update_fields=["status", "hold_expires_at"])
        snapshot = operations_snapshot(now=self.now)
        self.assertEqual(
            snapshot["holds"],
            {"overdue": 1, "oldest_overdue_seconds": 120, "legacy_without_deadline": 1},
        )
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "pending")

    def test_heartbeat_fencing_preserves_newer_run_and_records_success_failure(self):
        first = start_heartbeat("payment_scheduler")
        second = start_heartbeat("payment_scheduler")
        self.assertEqual(
            finish_heartbeat("payment_scheduler", first, succeeded=True, duration=10, processed=2),
            0,
        )
        self.assertEqual(OperationalHeartbeat.objects.get().status, "running")
        finish_heartbeat("payment_scheduler", second, succeeded=True, duration=2, processed=3)
        successful = OperationalHeartbeat.objects.get().last_success_at
        failed = start_heartbeat("payment_scheduler")
        finish_heartbeat("payment_scheduler", failed, succeeded=False, duration=1, processed=0)
        heartbeat = OperationalHeartbeat.objects.get()
        self.assertEqual(heartbeat.last_success_at, successful)
        self.assertEqual(heartbeat.status, "failed")
        snapshot = operations_snapshot()
        row = snapshot["heartbeats"][0]
        self.assertTrue(row["seen"])
        self.assertGreater(row["last_failure_timestamp"], 0)
        self.assertGreater(row["last_success_timestamp"], 0)
        self.assertNotIn(str(failed), json.dumps(snapshot))
        with self.assertRaises(ValueError):
            start_heartbeat("customer-controlled-label")

    @override_settings(PAYMENTS_SCHEDULER_SECRET="fixture-scheduler-" + "a" * 32)
    def test_scheduler_reports_empty_success_and_failure_only_after_authorization(self):
        factory = RequestFactory()
        self.assertEqual(tick(factory.post("/internal/payments/tick")).status_code, 401)
        self.assertEqual(
            tick(
                factory.post("/internal/payments/tick", HTTP_AUTHORIZATION="Bearer é")
            ).status_code,
            401,
        )
        self.assertFalse(OperationalHeartbeat.objects.exists())
        request = factory.post(
            "/internal/payments/tick", HTTP_AUTHORIZATION="Bearer fixture-scheduler-" + "a" * 32
        )
        with (
            patch("commerce.scheduler.schedule_due"),
            patch("commerce.scheduler.run_one", return_value=False),
        ):
            self.assertEqual(tick(request).status_code, 200)
        self.assertEqual(OperationalHeartbeat.objects.get().status, "succeeded")
        with patch(
            "commerce.scheduler.schedule_due", side_effect=RuntimeError("PRIVATE-EXCEPTION")
        ):
            with self.assertRaises(RuntimeError):
                tick(request)
        self.assertEqual(OperationalHeartbeat.objects.get().status, "failed")
        self.assertNotIn("PRIVATE", json.dumps(operations_snapshot()))

    def test_management_worker_reports_own_heartbeat(self):
        module = "commerce.management.commands.reconcile_payments"
        with patch(module + ".schedule_due"), patch(module + ".run_one", side_effect=[True, False]):
            call_command("reconcile_payments", limit=2, stdout=io.StringIO())
        heartbeat = OperationalHeartbeat.objects.get()
        self.assertEqual(heartbeat.name, "payment_worker")
        self.assertEqual(heartbeat.status, "succeeded")
        self.assertEqual(heartbeat.processed, 1)

    def test_worker_unexpected_error_at_retry_limit_requires_reconciliation(self):
        payment = self.payment()
        refund = RefundRequest.objects.create(
            payment=payment, amount=70, percent=70, status="submitted", actor_kind="guest"
        )
        job = PaymentJob.objects.create(
            payment=payment, kind="refund_verify", attempts=9, available_at=self.now
        )
        with patch("commerce.jobs.execute", side_effect=RuntimeError("PRIVATE-FAILURE")):
            self.assertTrue(run_one(provider=object()))
        job.refresh_from_db()
        refund.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(job.state, "dead")
        self.assertEqual(refund.status, "reconciliation_required")
        self.assertEqual(payment.status, "reconciliation_required")
        self.assertEqual(job.last_error, "payment_worker_error")
        self.assertNotIn("PRIVATE", refund.reconciliation_reason)

    def test_stale_worker_failure_cannot_mark_new_lease_for_reconciliation(self):
        payment = self.payment()
        PaymentJob.objects.create(payment=payment, kind="verify", attempts=9, available_at=self.now)
        old = claim()
        PaymentJob.objects.filter(pk=old.pk).update(lease_until=self.now - timedelta(seconds=1))
        current = claim()
        finish(old, ProviderError("fixture_permanent_error"))
        payment.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual(payment.status, "pending")
        self.assertEqual(current.state, "running")
        self.assertNotEqual(current.lease_token, old.lease_token)
