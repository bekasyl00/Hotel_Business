from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase


class HealthTests(TestCase):
    def test_liveness_does_not_require_database(self):
        with self.assertNumQueries(0):
            response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_readiness_uses_real_postgres(self):
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_database_failure_is_unavailable_without_details(self):
        with patch(
            "config.health.connection.cursor",
            side_effect=OperationalError("private connection details"),
        ):
            response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotContains(response, "private", status_code=503)
        self.assertEqual(self.client.post("/health/live").status_code, 405)
