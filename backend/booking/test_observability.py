import json
import time
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase, override_settings


@override_settings(METRICS_BEARER_TOKEN="fictional-monitoring-token-for-tests-only")
class ObservabilityTests(TestCase):
    def metrics(self, **kwargs):
        return self.client.get(
            "/internal/metrics",
            HTTP_AUTHORIZATION="Bearer fictional-monitoring-token-for-tests-only",
            **kwargs,
        )

    def test_auth_required_before_database_access_and_query_token_ignored(self):
        with self.assertNumQueries(0):
            denied = self.client.get(
                "/internal/metrics?token=fictional-monitoring-token-for-tests-only"
            )
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(
            self.client.get("/internal/metrics", HTTP_AUTHORIZATION="Bearer é").status_code, 401
        )
        self.assertIn("no-store", denied["Cache-Control"])
        self.assertEqual(self.client.post("/internal/metrics").status_code, 405)
        with override_settings(METRICS_BEARER_TOKEN=""):
            self.assertEqual(self.metrics().status_code, 404)

    def test_export_shared_gauges_not_process_local_request_counters(self):
        response = self.metrics()
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn("# TYPE tynys_database_connections gauge", text)
        self.assertIn("tynys_database_max_connections ", text)
        self.assertIn("tynys_worker_heartbeat_present", text)
        self.assertIn("tynys_metrics_collection_duration_seconds", text)
        timestamp = next(
            line
            for line in text.splitlines()
            if line.startswith("tynys_metrics_snapshot_timestamp_seconds ")
        )
        self.assertLess(abs(float(timestamp.split()[1]) - time.time()), 5)
        self.assertNotIn("http_requests_total", text)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("Set-Cookie", response.headers)

    def test_database_outage_fails_scrape_without_secret_details(self):
        with patch(
            "commerce.operations.operations_snapshot",
            side_effect=OperationalError("private database credential"),
        ):
            response = self.metrics()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("credential", response.content.decode())
        self.assertNotIn("tynys_payment_jobs 0", response.content.decode())

    @override_settings(REQUEST_LOG_ENABLED=True)
    def test_request_log_has_correlation_without_personal_data_or_path_values(self):
        with self.assertLogs("tynys.requests", level="INFO") as logs:
            response = self.client.get(
                "/api/v1/receipts/sensitive-id?iin=990101123456",
                HTTP_AUTHORIZATION="Bearer private-token",
                HTTP_X_REQUEST_ID="attacker-controlled-id",
            )
        record = json.loads(logs.records[-1].message)
        self.assertEqual(record["route"], "api/v1/receipts/<str:pk>")
        self.assertEqual(record["request_id"], response["X-Request-ID"])
        self.assertEqual(len(record["request_id"]), 32)
        self.assertGreaterEqual(record["duration_ms"], 0)
        self.assertEqual(record["status"], response.status_code)
        self.assertEqual(
            set(record), {"event", "request_id", "route", "method", "status", "duration_ms"}
        )
        serialized = json.dumps(record)
        for secret in ("990101123456", "sensitive-id", "private-token", "attacker-controlled-id"):
            self.assertNotIn(secret, serialized)

    @override_settings(REQUEST_LOG_ENABLED=True)
    def test_probes_do_not_fill_request_logs(self):
        with self.assertNoLogs("tynys.requests", level="INFO"):
            self.client.get("/health/live")
            self.metrics()
