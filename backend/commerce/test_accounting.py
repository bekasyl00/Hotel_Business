import json
import re
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from booking.models import Audit, Resort, User
from booking.test_helpers import unrelated_owner
from commerce.accounting.rendering import amount_words, pdf_bytes, xlsx_bytes
from commerce.accounting.services import prepare_after_stay
from commerce.models import AccountingDocument, DemoPayment, DocumentGuestRoster
from commerce.test_document_helpers import complete_roster, document_key
from commerce.tests import fixture

COMPANY = {
    "version": 0,
    "supplier": "Тестовая организация",
    "bin": "000000000000",
    "address": "Тестовый адрес",
    "vatMode": "no_vat",
    "vatRate": "0",
}


class AccountingTests(TestCase):
    def setUp(self):
        document_key(self)
        self.resort, self.booking, self.manager = fixture()
        self.accountant = User.objects.create_user(
            username="accountant@example.test",
            email="accountant@example.test",
            password="fictional-accountant-password",
            name="Бухгалтер",
            role="accountant",
            resort=self.resort,
        )
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.manager)
        self.csrf = self.client.get("/api/auth/csrf").json()["token"]

    def sign_in(self, user):
        self.client.force_login(user)
        self.csrf = self.client.get("/api/auth/csrf").json()["token"]

    def write(self, path, data, method="post"):
        return getattr(self.client, method)(path, data, format="json", HTTP_X_CSRFTOKEN=self.csrf)

    def paid(self):
        import uuid

        DemoPayment.objects.create(
            booking=self.booking,
            request_key=uuid.uuid4(),
            outcome="success",
            status="paid",
            amount=36000,
        )
        self.booking.checked_in_at = timezone.now() - timedelta(days=1)
        self.booking.checked_out_at = timezone.now()
        self.booking.save()
        complete_roster(self.booking, self.manager)

    def doc(self, kind="act"):
        response = self.write(
            "/api/accounting/documents", {"bookingId": self.booking.pk, "kind": kind}
        )
        self.assertEqual(response.status_code, 201, response.content)
        return AccountingDocument.objects.get(pk=response.json()["id"])

    def test_accountant_read_scope_and_no_operational_privileges(self):
        self.sign_in(self.accountant)
        self.assertEqual(self.client.get("/api/accounting?paymentMode=demo").status_code, 200)
        self.assertEqual(self.client.get("/api/workspace").status_code, 200)
        self.assertEqual(self.client.get("/api/analytics").status_code, 200)
        self.assertEqual(
            self.write(
                "/api/bookings/" + self.booking.pk + "/check-in", {"version": 1}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.write(
                "/api/resorts/" + self.resort.pk, {"version": 1, "name": "Changed"}, "patch"
            ).status_code,
            403,
        )
        other = Resort.objects.create(
            account=unrelated_owner(), name="Other", city="Test", address="Test", lat=42, lng=69
        )
        self.assertEqual(self.client.get("/api/accounting?resortId=" + other.pk).status_code, 200)
        self.assertEqual(
            self.write("/api/accounting/company/" + other.pk, COMPANY, "patch").status_code, 403
        )
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get("/api/accounting").status_code, 403)

    def test_csrf_hashing_and_sql_injection(self):
        self.sign_in(self.accountant)
        self.assertNotEqual(self.accountant.password, "fictional-accountant-password")
        self.assertTrue(self.accountant.check_password("fictional-accountant-password"))
        self.assertEqual(
            self.client.post(
                "/api/accounting/documents",
                {"bookingId": self.booking.pk, "kind": "act"},
                format="json",
            ).status_code,
            403,
        )
        data = self.client.get(
            "/api/accounting", {"search": "' OR 1=1; --", "paymentMode": "demo"}
        ).json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(User.objects.count(), 2)

    def test_admin_can_create_accountant_without_granting_management(self):
        self.manager.role = "admin"
        self.manager.save()
        self.client.force_login(self.manager)
        self.csrf = self.client.get("/api/auth/csrf").json()["token"]
        payload = {
            "name": "Тестовый бухгалтер",
            "login": "finance@example.test",
            "role": "accountant",
            "resortId": self.resort.pk,
            "status": "active",
            "password": "Fictional-test-secret-2026!",
        }
        response = self.write("/api/accounts", payload)
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(email=payload["login"])
        self.assertEqual(user.role, "accountant")
        self.assertTrue(user.check_password(payload["password"]))
        self.assertFalse(user.is_staff or user.is_superuser)
        self.client.force_login(user)
        self.assertEqual(self.client.get("/api/accounting").status_code, 200)
        self.assertEqual(self.client.get("/api/workspace").status_code, 200)

    def test_unknown_company_fields_return_validation_error(self):
        response = self.write(
            "/api/accounting/company/" + self.resort.pk, {**COMPANY, "isAdmin": True}, "patch"
        )
        self.assertEqual(response.status_code, 422)

    def test_document_preparation_is_idempotent_and_contains_no_original_personal_data(self):
        doc = self.doc()
        self.assertEqual(self.doc().pk, doc.pk)
        blob = xlsx_bytes(doc)
        wb = load_workbook(BytesIO(blob))
        self.assertEqual(wb.active["E9"].value, self.booking.guest_label)
        with ZipFile(BytesIO(blob)) as z:
            text = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
        self.assertFalse(re.findall(r"(?<![0-9])[0-9]{12}(?![0-9])", text))
        self.assertTrue(pdf_bytes(doc).startswith(b"%PDF"))
        self.assertEqual(AccountingDocument.objects.count(), 1)

    def test_actual_checkout_creates_only_act_and_invoice_drafts_once(self):
        self.paid()
        self.write(f"/api/accounting/company/{self.resort.pk}", COMPANY, "patch")
        self.booking.checked_out_at = None
        self.booking.save()
        self.client.force_login(self.manager)
        self.csrf = self.client.get("/api/auth/csrf").json()["token"]
        result = self.write(
            f"/api/bookings/{self.booking.pk}/check-out", {"version": self.booking.version}
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.booking.checked_out_at)
        prepare_after_stay(self.booking, self.manager)
        self.assertEqual(
            set(AccountingDocument.objects.values_list("kind", flat=True)), {"act", "invoice"}
        )
        self.assertFalse(AccountingDocument.objects.exclude(state="draft").exists())

    def test_money_words_and_environment_document_filter(self):
        self.assertEqual(amount_words(36000), "Тридцать шесть тысяч тенге 00 тиын")
        self.assertEqual(amount_words("21001.25"), "Двадцать одна тысяча один тенге 25 тиын")
        self.assertEqual(amount_words(111000), "Сто одиннадцать тысяч тенге 00 тиын")
        self.paid()
        self.doc()
        self.assertEqual(
            len(self.client.get("/api/accounting/documents?paymentMode=demo").json()["documents"]),
            1,
        )
        self.assertEqual(
            self.client.get("/api/accounting/documents?paymentMode=production").json()["documents"],
            [],
        )

    def test_release_requires_stay_company_payment_and_freezes_copy(self):
        doc = self.doc()
        url = "/api/accounting/documents/" + doc.pk + "/release"
        self.assertEqual(self.write(url, {"version": doc.version}).status_code, 409)
        self.paid()
        self.assertEqual(self.write(url, {"version": doc.version}).status_code, 409)
        self.assertEqual(
            self.write("/api/accounting/company/" + self.resort.pk, COMPANY, "patch").status_code,
            200,
        )
        result = self.write(url, {"version": doc.version})
        self.assertEqual(result.status_code, 200, result.content)
        doc.refresh_from_db()
        before = doc.snapshot.copy()
        self.booking.guest_label = "Changed"
        self.booking.save()
        self.assertEqual(
            self.write(
                "/api/accounting/documents/" + doc.pk + "/refresh", {"version": doc.version}
            ).status_code,
            409,
        )
        doc.refresh_from_db()
        self.assertEqual(doc.snapshot, before)
        self.assertEqual(
            self.write("/api/accounting/documents/" + doc.pk + "/void", {"version": 1}).status_code,
            409,
        )

    def test_guest_can_download_only_own_released_nonvoided_copy(self):
        self.paid()
        doc = self.doc()
        self.write("/api/accounting/company/" + self.resort.pk, COMPANY, "patch")
        self.write("/api/accounting/documents/" + doc.pk + "/release", {"version": doc.version})
        guest = APIClient()
        session = guest.session
        session["guest_owner"] = self.booking.owner
        session.save()
        path = "/api/my-documents/" + doc.pk + "/pdf/download"
        response = guest.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(APIClient().get(path).status_code, 404)
        self.assertEqual(guest.get("/api/accounting").status_code, 401)
        doc.refresh_from_db()
        self.write("/api/accounting/documents/" + doc.pk + "/void", {"version": doc.version})
        self.assertEqual(guest.get(path).status_code, 404)

    def test_cash_order_never_turns_bank_payment_into_cash(self):
        self.paid()
        doc = self.doc("cash_order")
        self.write("/api/accounting/company/" + self.resort.pk, COMPANY, "patch")
        self.assertEqual(
            self.write(
                "/api/accounting/documents/" + doc.pk + "/release", {"version": doc.version}
            ).status_code,
            409,
        )

    def test_spreadsheet_and_csv_formula_injection_remains_text(self):
        self.booking.guest_label = '=HYPERLINK("https://evil.invalid","x")'
        self.booking.save()
        doc = self.doc()
        cell = load_workbook(BytesIO(xlsx_bytes(doc))).active["E9"]
        self.assertEqual(cell.data_type, "s")
        self.sign_in(self.accountant)
        response = self.client.get("/api/accounting/export?paymentMode=demo")
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.content.decode())

    def test_company_versions_and_document_audit_exclude_requisites(self):
        path = "/api/accounting/company/" + self.resort.pk
        self.assertEqual(self.write(path, COMPANY, "patch").status_code, 200)
        self.assertEqual(self.write(path, COMPANY, "patch").status_code, 409)
        audits = json.dumps(
            list(Audit.objects.filter(entity="accountingCompany").values("before", "after"))
        )
        self.assertNotIn(COMPANY["bin"], audits)
        self.assertNotIn(COMPANY["supplier"], audits)

    def test_environment_totals_are_separate(self):
        self.sign_in(self.accountant)
        self.paid()
        self.assertEqual(
            self.client.get("/api/accounting?paymentMode=demo").json()["totals"]["received"], 36000
        )
        self.assertEqual(
            self.client.get("/api/accounting?paymentMode=production").json()["totals"]["received"],
            0,
        )

    def test_manager_can_read_booking_documents_without_financial_write_access(self):
        doc = self.doc()
        self.client.force_login(self.manager)
        base = f"/api/bookings/{self.booking.pk}/documents"
        self.assertEqual([d["id"] for d in self.client.get(base).json()], [doc.pk])
        for ext, prefix in [("pdf", b"%PDF"), ("xlsx", b"PK")]:
            response = self.client.get(f"{base}/{doc.pk}/{ext}/download")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(prefix))
            self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.get("/api/accounting").status_code, 403)
        self.assertEqual(self.client.post(base, {}).status_code, 403)  # CSRF is still enforced
        other = Resort.objects.create(
            account=unrelated_owner(), name="Other", city="Test", address="Test", lat=1, lng=1
        )
        Resort.objects.filter(account=self.manager).update(account=unrelated_owner())
        other.account = self.manager
        other.save(update_fields=["account"])
        self.manager.resort = other
        self.manager.save()
        self.assertEqual(self.client.get(base).status_code, 404)
        self.assertEqual(self.client.get(f"{base}/{doc.pk}/pdf/download").status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(base).status_code, 401)

    def test_document_workspace_and_all_file_operations_are_operational_only(self):
        doc = self.doc()
        path = f"/api/accounting/documents/{doc.pk}"
        workspace = self.client.get("/api/accounting/documents", {"paymentMode": "demo"})
        self.assertEqual(workspace.status_code, 200)
        self.assertEqual([row["id"] for row in workspace.json()["bookings"]], [self.booking.pk])
        self.assertIsNone(workspace.json()["bookings"][0]["checkedOutAt"])
        self.assertEqual(self.write(path + "/refresh", {"version": doc.version}).status_code, 200)
        self.sign_in(self.accountant)
        for url in (
            "/api/accounting/documents",
            path + "/pdf/download",
            path + "/xlsx/download",
            f"/api/bookings/{self.booking.pk}/documents",
            f"/api/bookings/{self.booking.pk}/documents/{doc.pk}/pdf/download",
            f"/api/bookings/{self.booking.pk}/document-guests",
            f"/api/accounting/company/{self.resort.pk}",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.write(
                "/api/accounting/documents", {"bookingId": self.booking.pk, "kind": "invoice"}
            ).status_code,
            403,
        )
        for action in ("release", "refresh", "void"):
            self.assertEqual(self.write(path + "/" + action, {"version": 2}).status_code, 403)
        finance = self.client.get("/api/accounting?paymentMode=demo")
        self.assertEqual(finance.status_code, 200)
        self.assertEqual(finance.json()["documents"], [])
        self.assertEqual(
            self.client.get("/api/accounting/export?paymentMode=demo").status_code, 200
        )
        other = unrelated_owner()
        self.sign_in(other)
        self.assertEqual(self.client.get("/api/accounting/documents").json()["count"], 0)
        self.assertEqual(self.client.get(path + "/pdf/download").status_code, 404)
        self.assertEqual(self.write(path + "/refresh", {"version": 2}).status_code, 404)
        self.assertEqual(
            self.write(
                "/api/accounting/documents", {"bookingId": self.booking.pk, "kind": "invoice"}
            ).status_code,
            404,
        )

    def test_delivery_defaults_manual_and_legacy_company_edits_preserve_setting(self):
        path = f"/api/staff-profile/company/{self.resort.pk}"
        self.assertEqual(self.client.get(path).json()["documentDelivery"], "manual")
        self.assertEqual(
            self.write(path, {**COMPANY, "documentDelivery": "invalid"}, "patch").status_code, 422
        )
        response = self.write(path, {**COMPANY, "documentDelivery": "automatic"}, "patch")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["documentDelivery"], "automatic")
        response = self.write(
            path, {**COMPANY, "version": 1, "supplier": "Updated issuer"}, "patch"
        )
        self.assertEqual(response.json()["documentDelivery"], "automatic")
        self.assertEqual(
            self.client.get(f"/api/accounting/company/{self.resort.pk}").json()["version"], 2
        )

    def test_automatic_delivery_releases_after_actual_checkout_once(self):
        self.paid()
        self.booking.checked_out_at = None
        self.booking.save()
        self.write(
            f"/api/accounting/company/{self.resort.pk}",
            {**COMPANY, "documentDelivery": "automatic"},
            "patch",
        )
        doc = self.doc()
        self.assertEqual(doc.state, "draft")
        self.assertEqual(
            self.write(f"/api/accounting/documents/{doc.pk}/release", {"version": 1}).status_code,
            409,
        )
        result = self.write(
            f"/api/bookings/{self.booking.pk}/check-out", {"version": self.booking.version}
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.booking.refresh_from_db()
        docs = list(AccountingDocument.objects.order_by("kind"))
        self.assertEqual(
            [(d.kind, d.state) for d in docs], [("act", "released"), ("invoice", "released")]
        )
        self.assertTrue(all(d.released_at and d.snapshot["checkedOutAt"] for d in docs))
        before = [(d.pk, d.version, d.snapshot) for d in docs]
        prepare_after_stay(self.booking, self.manager)
        after = [(d.pk, d.version, d.snapshot) for d in AccountingDocument.objects.order_by("kind")]
        self.assertEqual(before, after)
        self.assertEqual(
            Audit.objects.filter(entity="accountingDocuments", action="release").count(), 2
        )

    def test_incomplete_automatic_documents_do_not_undo_checkout(self):
        self.paid()
        DocumentGuestRoster.objects.filter(booking=self.booking).delete()
        self.booking.checked_out_at = None
        self.booking.save()
        self.write(
            f"/api/accounting/company/{self.resort.pk}",
            {**COMPANY, "documentDelivery": "automatic"},
            "patch",
        )
        result = self.write(
            f"/api/bookings/{self.booking.pk}/check-out", {"version": self.booking.version}
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.booking.checked_out_at)
        self.assertEqual(AccountingDocument.objects.filter(state="draft").count(), 2)
        self.assertFalse(AccountingDocument.objects.filter(state="released").exists())
        complete_roster(self.booking, self.manager)
        doc = AccountingDocument.objects.get(kind="act")
        self.assertEqual(
            self.write(
                f"/api/accounting/documents/{doc.pk}/release", {"version": doc.version}
            ).status_code,
            200,
        )

    def test_unavailable_document_key_does_not_undo_checkout_or_publish_identity(self):
        self.paid()
        self.booking.checked_out_at = None
        self.booking.save()
        self.write(
            f"/api/accounting/company/{self.resort.pk}",
            {**COMPANY, "documentDelivery": "automatic"},
            "patch",
        )
        with override_settings(DOCUMENT_DATA_ENCRYPTION_KEYS=[]):
            result = self.write(
                f"/api/bookings/{self.booking.pk}/check-out", {"version": self.booking.version}
            )
        self.assertEqual(result.status_code, 200, result.content)
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.booking.checked_out_at)
        self.assertFalse(AccountingDocument.objects.exists())
        deferred = Audit.objects.filter(entity="accountingDocuments", action="delivery_deferred")
        self.assertEqual(deferred.count(), 2)
        self.assertTrue(all(set(a.after) == {"kind", "reason"} for a in deferred))

    def test_guest_read_and_download_check_actual_checkout_in_addition_to_release(self):
        self.paid()
        doc = self.doc()
        self.write(f"/api/accounting/company/{self.resort.pk}", COMPANY, "patch")
        self.assertEqual(
            self.write(
                f"/api/accounting/documents/{doc.pk}/release", {"version": doc.version}
            ).status_code,
            200,
        )
        guest = APIClient()
        session = guest.session
        session["guest_owner"] = self.booking.owner
        session.save()
        self.assertEqual(len(guest.get("/api/my-documents").json()), 1)
        self.booking.checked_out_at = None
        self.booking.save()
        self.assertEqual(guest.get("/api/my-documents").json(), [])
        for kind in ("pdf", "xlsx"):
            self.assertEqual(
                guest.get(f"/api/my-documents/{doc.pk}/{kind}/download").status_code, 404
            )
        self.booking.checked_out_at = timezone.now()
        self.booking.status = "cancelled"
        self.booking.save()
        self.assertEqual(guest.get("/api/my-documents").json(), [])
