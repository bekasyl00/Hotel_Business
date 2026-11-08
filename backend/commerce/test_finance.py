import uuid
from datetime import timedelta
from io import BytesIO

from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from booking.models import Audit, Resort, User
from booking.test_helpers import unrelated_owner
from commerce.models import AccountingExpense, DemoPayment
from commerce.tests import fixture


class FinanceTests(TestCase):
    def setUp(self):
        self.resort, self.booking, self.manager = fixture()
        self.user = User.objects.create_user(
            username="finance@fictional.test",
            role="accountant",
            resort=None,
            password="Fictional-only-2026!",
        )
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.csrf = self.client.get("/api/auth/csrf").json()["token"]
        self.payload = dict(
            resortId=None,
            date=str(timezone.localdate()),
            amount=1250,
            category="operations",
            description='=HYPERLINK("https://example.test")',
            paymentMode="demo",
            requestId=str(uuid.uuid4()),
        )

    def post(self, path, data):
        return self.client.post(path, data, format="json", HTTP_X_CSRFTOKEN=self.csrf)

    def create(self, **changes):
        return self.post("/api/accounting/expenses", {**self.payload, **changes})

    def report(self, **params):
        return self.client.get("/api/accounting", {"paymentMode": "demo", **params})

    def test_global_accountant_reads_all_properties_and_has_no_operational_writes(self):
        Resort.objects.create(
            account=unrelated_owner(), name="Other", city="Test", address="Test", lat=1, lng=1
        )
        workspace = self.client.get("/api/workspace")
        self.assertEqual(workspace.status_code, 200)
        self.assertEqual(len(workspace.json()["resorts"]), 2)
        self.assertEqual(workspace.json()["accounts"], [])
        self.assertEqual(workspace.json()["audit"], [])
        self.assertEqual(self.client.get("/api/analytics").status_code, 200)
        self.assertEqual(len(self.report().json()["resorts"]), 2)
        for path, data in [
            ("/bookings", {}),
            ("/bookings/" + self.booking.pk + "/notes", {"version": 1, "staffNotes": "blocked"}),
            ("/accounts", {}),
            ("/resorts", {}),
        ]:
            self.assertEqual(self.post("/api" + path, data).status_code, 403)

    def test_expense_idempotency_void_version_and_mode_isolation(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.content)
        item = r.json()
        self.assertEqual(self.create().json()["id"], item["id"])
        self.assertEqual(self.create(amount=1251).status_code, 409)
        self.assertEqual(AccountingExpense.objects.count(), 1)
        self.assertEqual(Audit.objects.filter(entity="accountingExpenses").count(), 1)
        self.assertEqual(self.report().json()["totals"]["expenses"], 1250)
        self.assertEqual(self.report(paymentMode="production").json()["totals"]["expenses"], 0)
        self.assertEqual(self.report(resortId=self.resort.pk).json()["totals"]["expenses"], 0)
        url = "/api/accounting/expenses/" + item["id"] + "/void"
        self.assertEqual(self.post(url, {"version": 0, "reason": "duplicate"}).status_code, 409)
        self.assertEqual(self.post(url, {"version": 1, "reason": "duplicate"}).status_code, 200)
        self.assertEqual(self.report().json()["totals"]["expenses"], 0)
        self.assertEqual(self.post(url, {"version": 1, "reason": "duplicate"}).status_code, 409)
        self.assertEqual(AccountingExpense.objects.count(), 1)

    def test_finance_uses_server_amounts_and_export_strings_are_not_formulas(self):
        self.booking.snapshot["commissionTerms"] = {"amount": 3600}
        self.booking.save()
        DemoPayment.objects.create(
            booking=self.booking,
            request_key=uuid.uuid4(),
            outcome="success",
            status="paid",
            amount=36000,
        )
        self.create(resortId=self.resort.pk)
        response = self.report()
        self.assertEqual(response.status_code, 200, response.content)
        totals = response.json()["totals"]
        self.assertEqual(totals["received"], 36000)
        self.assertEqual(totals["net"], 36000)
        self.assertEqual(totals["confirmedUnpaid"], 0)
        self.assertEqual(totals["commissionEstimate"], 3600)
        self.assertEqual(totals["expenses"], 1250)
        export = self.client.get("/api/accounting/report.xlsx?paymentMode=demo")
        self.assertEqual(export.status_code, 200, export.content[:200])
        workbook = load_workbook(BytesIO(export.content))
        self.assertEqual(workbook.sheetnames, ["Сводка", "Санатории", "Расходы"])
        self.assertEqual(workbook["Расходы"]["F2"].data_type, "s")
        self.assertEqual(workbook["Расходы"]["F2"].value, self.payload["description"])

    def test_invalid_expenses_csrf_and_manager_denied(self):
        for changes in [
            {"amount": 0},
            {"amount": -1},
            {"amount": 1.5},
            {"paymentMode": "live"},
            {"category": "sql"},
            {"date": str(timezone.localdate() + timedelta(days=1))},
            {"unknown": "x"},
        ]:
            self.assertEqual(self.create(**changes).status_code, 422)
        self.assertEqual(
            self.client.post("/api/accounting/expenses", self.payload, format="json").status_code,
            403,
        )
        self.client.force_login(self.manager)
        self.csrf = self.client.get("/api/auth/csrf").json()["token"]
        self.assertEqual(self.create().status_code, 403)
        self.assertEqual(AccountingExpense.objects.count(), 0)
