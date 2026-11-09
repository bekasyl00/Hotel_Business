import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.db import close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import LoginAttempt, User
from .rate_limits import (
    RateLimited,
    client_ip,
    consume_limits,
    enforce_limit,
    prune_limits,
    quota_key,
)
from .tests import authenticate_guest


class SharedQuotaTests(TestCase):
    def test_window_expiry_and_retry_after_are_exact_at_boundary(self):
        now = timezone.now()
        key = quota_key("test-window")
        with patch("booking.rate_limits.timezone.now", return_value=now):
            consume_limits([(key, 1)], minutes=1)
        with patch("booking.rate_limits.timezone.now", return_value=now + timedelta(seconds=30)):
            with self.assertRaises(RateLimited) as limited:
                consume_limits([(key, 1)], minutes=1)
        self.assertEqual(limited.exception.wait, 30)
        with patch("booking.rate_limits.timezone.now", return_value=now + timedelta(minutes=1)):
            consume_limits([(key, 1)], minutes=1)
        self.assertEqual(LoginAttempt.objects.get(pk=key).count, 1)

    def test_rejection_does_not_rollback_other_counters(self):
        limited, secondary = quota_key("limited"), quota_key("secondary")
        LoginAttempt.objects.create(key=limited, count=1, since=timezone.now())
        with self.assertRaises(RateLimited):
            consume_limits([(limited, 1), (secondary, 10)])
        self.assertEqual(LoginAttempt.objects.get(pk=secondary).count, 1)

    def test_untrusted_forwarded_address_cannot_reset_quota(self):
        request = SimpleNamespace(META={"REMOTE_ADDR": "192.0.2.10"})
        enforce_limit(request, "test-proxy", ip_limit=1)
        request.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.1"
        request.META["HTTP_X_REAL_IP"] = "198.51.100.2"
        with self.assertRaises(RateLimited):
            enforce_limit(request, "test-proxy", ip_limit=1)
        self.assertEqual(LoginAttempt.objects.count(), 1)
        self.assertNotIn("192.0.2.10", LoginAttempt.objects.get().key)

    def test_vercel_header_is_trusted_only_with_server_runtime_flag(self):
        request = SimpleNamespace(META={
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_X_VERCEL_FORWARDED_FOR": "198.51.100.7",
            "HTTP_X_FORWARDED_FOR": "192.0.2.9",
            "HTTP_X_REAL_IP": "192.0.2.10",
        })
        with override_settings(VERCEL_RUNTIME=False):
            self.assertEqual(client_ip(request), "127.0.0.1")
        with override_settings(VERCEL_RUNTIME=True):
            self.assertEqual(client_ip(request), "198.51.100.7")
            enforce_limit(request, "trusted-vercel", ip_limit=1)
            self.assertTrue(LoginAttempt.objects.filter(
                pk=quota_key("trusted-vercel:ip:198.51.100.7")
            ).exists())
            request.META["HTTP_X_VERCEL_FORWARDED_FOR"] = "2001:DB8:0:0::1"
            self.assertEqual(client_ip(request), "2001:db8::1")

    @override_settings(VERCEL_RUNTIME=True)
    def test_malformed_or_chained_vercel_header_falls_back_to_socket_address(self):
        for value in (
            "198.51.100.7, 192.0.2.1", "", None, "192.0.2.999", "١٩٢.0.2.1",
            "x" * 100, "fe80::1%eth0", " 198.51.100.7", "198.51.100.7\n",
        ):
            with self.subTest(value=value):
                request = SimpleNamespace(META={
                    "REMOTE_ADDR": "127.0.0.1", "HTTP_X_VERCEL_FORWARDED_FOR": value,
                    "HTTP_X_FORWARDED_FOR": "192.0.2.8",
                })
                self.assertEqual(client_ip(request), "127.0.0.1")

    def test_staff_login_returns_standard_retry_after_and_machine_code(self):
        key = hashlib.sha256(b"email:operator@example.test").hexdigest()
        LoginAttempt.objects.create(key=key, count=30, since=timezone.now())
        result = APIClient().post(
            "/api/auth/login", {"email": "operator@example.test", "password": "wrong"},
            format="json",
        )
        self.assertEqual(result.status_code, 429)
        self.assertEqual(result.json()["code"], "rate_limited")
        self.assertTrue(1 <= int(result["Retry-After"]) <= 900)
        self.assertIn("no-store", result["Cache-Control"])

    def test_failed_booking_still_consumes_authenticated_quota_across_api_versions(self):
        client = APIClient()
        account = authenticate_guest(client)
        key = quota_key("booking-create:subject:guest:" + str(account.pk))
        LoginAttempt.objects.create(key=key, count=29, since=timezone.now())
        invalid = client.post("/api/v1/my-bookings", {}, format="json")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(LoginAttempt.objects.get(pk=key).count, 30)
        limited = client.post("/api/my-bookings", {}, format="json")
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.json()["code"], "rate_limited")

    def test_staff_cookie_does_not_replace_guest_booking_quota(self):
        client = APIClient()
        guest = authenticate_guest(client)
        employee = User.objects.create_user(username="staff-cookie@example.test")
        client.force_authenticate(employee)
        LoginAttempt.objects.create(
            key=quota_key("booking-create:subject:guest:" + str(guest.pk)),
            count=30,
            since=timezone.now(),
        )
        self.assertEqual(client.post("/api/my-bookings", {}, format="json").status_code, 429)

    def test_availability_limit_runs_before_expensive_read_and_is_shared(self):
        key = quota_key("availability-read:ip:127.0.0.1")
        LoginAttempt.objects.create(key=key, count=300, since=timezone.now())
        with patch("booking.views.availability_calendar") as calculation:
            response = APIClient().get("/api/v1/availability-calendar")
            self.assertEqual(response.status_code, 429)
            calculation.assert_not_called()
        self.assertEqual(APIClient().get("/api/availability").status_code, 429)

    def test_export_quota_precedes_financial_aggregation(self):
        client = APIClient()
        accountant = User.objects.create_user(username="quota@example.test", role="accountant")
        client.force_authenticate(accountant)
        LoginAttempt.objects.create(
            key=quota_key("accounting-download:ip:127.0.0.1"), count=60, since=timezone.now()
        )
        with patch("commerce.accounting.views.financial_report") as aggregate:
            self.assertEqual(client.get("/api/accounting/report.xlsx").status_code, 429)
            aggregate.assert_not_called()

    def test_denied_roster_read_keeps_quota_outside_domain_transaction(self):
        client = APIClient()
        response = client.get("/api/bookings/missing/document-guests")
        self.assertEqual(response.status_code, 401)
        row = LoginAttempt.objects.get(pk=quota_key("document-guests-read:ip:127.0.0.1"))
        self.assertEqual(row.count, 1)

    def test_cleanup_is_dry_run_bounded_and_keeps_active_windows(self):
        old = timezone.now() - timedelta(days=8)
        for key in ("old-a", "old-b", "old-c"):
            LoginAttempt.objects.create(key=quota_key(key), count=30, since=old)
        consume_limits([(quota_key("active"), 1)])
        output = StringIO()
        call_command("cleanup_rate_limits", limit=2, stdout=output)
        self.assertIn("dry run", output.getvalue())
        self.assertEqual(LoginAttempt.objects.count(), 4)
        self.assertEqual(prune_limits(limit=2, delete=True), 2)
        self.assertEqual(LoginAttempt.objects.count(), 2)
        with self.assertRaises(RateLimited):
            consume_limits([(quota_key("active"), 1)])
        with self.assertRaises(ValueError):
            prune_limits(days=0, delete=True)

    def test_challenge_scope_is_touched_and_can_be_recreated_after_cleanup(self):
        from .guest_auth import lock_identity_scope

        phone = "+77000000001"
        key = quota_key("guest-challenge:" + phone)
        LoginAttempt.objects.create(key=key, since=timezone.now() - timedelta(days=8))
        with transaction.atomic():
            lock_identity_scope(phone, timezone.now())
        self.assertEqual(prune_limits(delete=True), 0)
        LoginAttempt.objects.filter(pk=key).update(since=timezone.now() - timedelta(days=8))
        self.assertEqual(prune_limits(delete=True), 1)
        with transaction.atomic():
            lock_identity_scope(phone, timezone.now())
        self.assertTrue(LoginAttempt.objects.filter(pk=key).exists())


class SharedQuotaConcurrencyTests(TransactionTestCase):
    def test_cleanup_skips_a_scope_currently_locked_by_another_worker(self):
        key = quota_key("locked-scope")
        LoginAttempt.objects.create(key=key, since=timezone.now() - timedelta(days=8))
        ready = Barrier(2)

        def hold():
            close_old_connections()
            try:
                with transaction.atomic():
                    LoginAttempt.objects.select_for_update().get(pk=key)
                    ready.wait(timeout=10)
                    ready.wait(timeout=10)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(hold)
            ready.wait(timeout=10)
            try:
                self.assertEqual(prune_limits(delete=True), 0)
            finally:
                ready.wait(timeout=10)
            future.result(timeout=10)
        self.assertEqual(prune_limits(delete=True), 1)

    def test_parallel_workers_cannot_exceed_limit(self):
        key = quota_key("parallel-limit")
        ready = Barrier(2)

        def consume():
            close_old_connections()
            try:
                ready.wait(timeout=10)
                try:
                    consume_limits([(key, 1)])
                    return "accepted"
                except RateLimited:
                    return "limited"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: consume(), range(2)))
        self.assertCountEqual(results, ["accepted", "limited"])
        self.assertEqual(LoginAttempt.objects.get(pk=key).count, 1)
