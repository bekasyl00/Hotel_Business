import json

from django.test import TestCase
from rest_framework.test import APIClient

from commerce.models import AccountingCompany, AccountingDocument
from commerce.test_accounting import COMPANY
from commerce.tests import fixture

from .authentication import staff_credential_version
from .models import Audit, Resort, User
from .test_staff_mobile_auth import bearer
from .test_staff_mobile_auth import login as native_login
from .tests import PASSWORD


class StaffProfileTests(TestCase):
    def setUp(self):
        self.resort, self.booking, self.manager = fixture()
        self.manager.set_password(PASSWORD)
        self.manager.save()
        self.admin = User.objects.create_user(
            username="admin@example.test",
            email="admin@example.test",
            password=PASSWORD,
            role="admin",
        )
        self.accountant = User.objects.create_user(
            username="accountant@example.test",
            email="accountant@example.test",
            password=PASSWORD,
            role="accountant",
        )
        self.foreign = Resort.objects.create(
            account=self.admin, name="Other resort", lat=42, lng=69
        )
        self.api = APIClient(enforce_csrf_checks=True)
        self.sign_in(self.manager)

    def sign_in(self, user):
        self.api.force_login(user)
        self.csrf = self.api.get("/api/auth/csrf").json()["token"]

    def patch(self, path, data):
        return self.api.patch(path, data, format="json", HTTP_X_CSRFTOKEN=self.csrf)

    def fields(self, **extra):
        return {
            "name": "Fictional Employee",
            "jobTitle": "Reception",
            "contactPhone": "+7 (700) 000-00-00",
            "version": 1,
            "accountVersion": 1,
            **extra,
        }

    def test_self_edit_uses_separate_version_and_preserves_authenticated_sessions(self):
        original = staff_credential_version(self.manager)
        native = native_login(self.manager).json()
        result = self.patch("/api/staff-profile", self.fields())
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["profile"]["contactPhone"], "+77000000000")
        self.assertEqual(result.json()["profile"]["version"], 2)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.version, 1)
        self.assertEqual(self.manager.profile_version, 2)
        self.assertEqual(self.manager.name, "Fictional Employee")
        self.assertEqual(self.manager.email, "payments@example.test")
        self.assertEqual(original, staff_credential_version(self.manager))
        self.assertEqual(self.api.get("/api/workspace").status_code, 200)
        self.assertEqual(
            bearer(native["accessToken"]).get("/api/v1/staff-profile").status_code, 200
        )
        self.assertEqual(self.patch("/api/staff-profile", self.fields()).status_code, 409)
        audit = Audit.objects.get(entity="staffProfile")
        self.assertEqual(audit.before, {"version": 1})
        self.assertEqual(audit.after, {"version": 2})
        self.assertNotIn("77000000000", json.dumps(audit.after))
        self.assertNotIn("Fictional", audit.actor)

    def test_profile_scope_and_privilege_fields_are_protected(self):
        own = self.api.get("/api/v1/staff-profile")
        self.assertEqual([r["id"] for r in own.json()["resorts"]], [self.resort.pk])
        for field, value in [
            ("role", "admin"),
            ("login", "changed@example.test"),
            ("id", self.admin.pk),
            ("iin", "000000000000"),
        ]:
            with self.subTest(field=field):
                self.assertEqual(
                    self.patch("/api/staff-profile", self.fields(**{field: value})).status_code, 422
                )
        self.assertEqual(
            self.api.patch("/api/staff-profile", self.fields(), format="json").status_code, 403
        )
        self.assertEqual(
            self.patch("/api/staff-profile", self.fields(contactPhone="invalid")).status_code, 422
        )
        self.assertEqual(
            self.patch("/api/staff-profile", self.fields(accountVersion=2)).status_code, 409
        )
        self.assertEqual(APIClient().get("/api/staff-profile").status_code, 401)
        self.sign_in(self.accountant)
        self.assertEqual(len(self.api.get("/api/staff-profile").json()["resorts"]), 2)
        self.assertEqual(self.patch("/api/staff-profile", self.fields()).status_code, 200)
        self.accountant.refresh_from_db()
        self.assertEqual(self.accountant.role, "accountant")

    def test_admin_and_self_name_edits_detect_stale_profile_versions(self):
        self.assertEqual(self.patch("/api/staff-profile", self.fields()).status_code, 200)
        self.sign_in(self.admin)
        body = {
            "version": 1,
            "profileVersion": 1,
            "name": "Admin corrected name",
            "login": self.manager.email,
            "role": "manager",
            "status": "active",
        }
        self.assertEqual(self.patch(f"/api/accounts/{self.manager.pk}", body).status_code, 409)
        without_profile_version = {
            key: value for key, value in body.items() if key != "profileVersion"
        }
        self.assertEqual(
            self.patch(f"/api/accounts/{self.manager.pk}", without_profile_version).status_code,
            409,
        )
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.name, "Fictional Employee")
        self.assertEqual(self.manager.version, 1)
        body["profileVersion"] = 2
        changed = self.patch(f"/api/accounts/{self.manager.pk}", body)
        self.assertEqual(changed.status_code, 200, changed.content)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.profile_version, 3)
        self.sign_in(self.manager)
        self.assertEqual(
            self.patch("/api/staff-profile", self.fields(version=2, accountVersion=2)).status_code,
            409,
        )

    def test_admin_legacy_payload_without_name_change_can_keep_profile_version_omitted(self):
        self.assertEqual(self.patch("/api/staff-profile", self.fields()).status_code, 200)
        self.sign_in(self.admin)
        result = self.patch(
            f"/api/accounts/{self.manager.pk}",
            {
                "version": 1,
                "name": "Fictional Employee",
                "login": "changed@example.test",
                "role": "manager",
                "status": "active",
            },
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.email, "changed@example.test")
        self.assertEqual(self.manager.profile_version, 2)

    def test_owned_issuer_settings_are_shared_only_with_operational_staff(self):
        path = f"/api/staff-profile/company/{self.resort.pk}"
        self.assertEqual(self.api.get(path).json()["version"], 0)
        saved = self.patch(path, COMPANY)
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(
            AccountingCompany.objects.get(resort=self.resort).details["supplier"],
            COMPANY["supplier"],
        )
        self.assertEqual(self.patch(path, COMPANY).status_code, 409)
        self.assertEqual(
            self.api.get(f"/api/staff-profile/company/{self.foreign.pk}").status_code, 403
        )
        self.assertEqual(
            self.patch(f"/api/staff-profile/company/{self.foreign.pk}", COMPANY).status_code, 403
        )
        self.assertEqual(self.api.get("/api/accounting").status_code, 403)
        shared = self.api.get(f"/api/accounting/company/{self.resort.pk}")
        self.assertEqual(shared.status_code, 200)
        self.assertEqual(shared.json()["supplier"], COMPANY["supplier"])
        self.assertEqual(
            self.patch(
                f"/api/accounting/company/{self.resort.pk}", {**COMPANY, "version": 1}
            ).status_code,
            200,
        )
        prepared = self.api.post(
            "/api/accounting/documents",
            {"bookingId": self.booking.pk, "kind": "act"},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(prepared.status_code, 201)
        self.sign_in(self.accountant)
        self.assertEqual(self.api.get(f"/api/accounting/company/{self.resort.pk}").status_code, 403)
        self.assertEqual(
            self.api.get(f"/api/staff-profile/company/{self.resort.pk}").status_code, 403
        )
        self.assertEqual(
            self.patch(f"/api/staff-profile/company/{self.foreign.pk}", COMPANY).status_code, 403
        )
        for event in Audit.objects.filter(entity="accountingCompany"):
            self.assertEqual(set(event.after), {"version"})

    def test_company_validation_csrf_and_released_snapshots(self):
        path = f"/api/staff-profile/company/{self.resort.pk}"
        self.assertEqual(self.api.patch(path, COMPANY, format="json").status_code, 403)
        for extra in [
            {"bin": "12"},
            {"vatMode": "included", "vatRate": "0"},
            {"iban": "not-an-account"},
            {"role": "admin"},
        ]:
            self.assertEqual(self.patch(path, {**COMPANY, **extra}).status_code, 422)
        old = {"supplier": "Frozen company", "bin": "000000000000", "amount": 36000}
        for kind in ("act", "invoice", "cash_order"):
            AccountingDocument.objects.create(
                booking=self.booking,
                kind=kind,
                number="TEST-" + kind,
                state="released",
                snapshot=old,
                created_by=self.accountant,
            )
        self.assertEqual(self.patch(path, COMPANY).status_code, 200)
        self.assertEqual(
            self.patch(path, {**COMPANY, "version": 1, "supplier": "New company"}).status_code, 200
        )
        for doc in AccountingDocument.objects.all():
            self.assertEqual(doc.snapshot, old)
            self.assertEqual(doc.state, "released")
            self.assertEqual(doc.version, 1)
