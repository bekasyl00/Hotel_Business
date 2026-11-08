from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .authentication import staff_credential_version
from .models import Audit, GuestAccount, Resort, User
from .tests import PASSWORD, authenticate_guest, fixture


class DirectoryTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.api = APIClient(enforce_csrf_checks=True)
        self.api.force_login(self.admin)
        self.token = self.api.get("/api/auth/csrf").json()["token"]

    def write(self, method, path, data):
        return getattr(self.api, method)(path, data, format="json", HTTP_X_CSRFTOKEN=self.token)

    @override_settings(DEBUG=True)
    def test_seed_accepts_first_superuser_with_default_manager_role(self):
        from io import StringIO

        from django.core.management import call_command

        self.admin.role = "manager"
        self.admin.is_superuser = True
        self.admin.save()
        call_command("seed_demo", stdout=StringIO())
        self.assertGreater(Resort.objects.filter(account=self.admin).count(), 0)
        self.assertFalse(Resort.objects.filter(account__isnull=True).exists())

    def test_resort_requires_owner_in_database_and_api(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Resort.objects.create(name="No owner", lat=1, lng=1)
        self.assertEqual(
            self.write(
                "post",
                "/api/resorts",
                {"name": "No owner", "lat": 1, "lng": 1, "city": "Test", "address": "Test"},
            ).status_code,
            422,
        )
        self.assertEqual(Resort.objects.filter(account__isnull=True).count(), 0)

    def test_one_manager_multiple_resorts_and_transfer_revokes_old_access(self):
        other = Resort.objects.create(name="Second", lat=1, lng=1, account=self.manager)
        manager_api = APIClient()
        manager_api.force_login(self.manager)
        self.assertEqual(
            set(r["id"] for r in manager_api.get("/api/workspace").json()["resorts"]),
            {self.resort.pk, other.pk},
        )
        old_fingerprint = staff_credential_version(self.manager)
        response = self.write(
            "patch", f"/api/resorts/{self.resort.pk}", {"version": 1, "accountId": self.admin.pk}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.manager.refresh_from_db()
        self.assertNotEqual(old_fingerprint, staff_credential_version(self.manager))
        self.assertEqual(
            [r["id"] for r in manager_api.get("/api/workspace").json()["resorts"]], [other.pk]
        )
        self.assertEqual(self.manager.resort_id, self.resort.pk)  # Legacy value confers no access.
        self.api.force_login(self.manager)
        self.token = self.api.get("/api/auth/csrf").json()["token"]
        self.assertEqual(
            self.write(
                "patch", f"/api/rooms/{self.room.pk}", {"version": 1, "price": 1}
            ).status_code,
            403,
        )

    def test_manager_cannot_change_ownership_and_public_catalog_hides_it(self):
        self.api.force_login(self.manager)
        self.token = self.api.get("/api/auth/csrf").json()["token"]
        self.assertEqual(
            self.write(
                "patch",
                f"/api/resorts/{self.resort.pk}",
                {"version": 1, "accountId": self.admin.pk},
            ).status_code,
            403,
        )
        public = APIClient().get(f"/api/resorts/{self.resort.pk}").json()
        self.assertNotIn("accountId", public["resort"])

    def test_manager_can_round_trip_unchanged_owner_from_older_clients(self):
        self.api.force_login(self.manager)
        self.token = self.api.get("/api/auth/csrf").json()["token"]
        response = self.write(
            "patch",
            f"/api/resorts/{self.resort.pk}",
            {
                "version": 1,
                "accountId": self.manager.pk,
                "description": "Updated description",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["accountId"], self.manager.pk)

    def test_account_can_be_created_before_any_resorts(self):
        result = self.write(
            "post",
            "/api/accounts",
            {
                "name": "New partner",
                "login": "partner@example.test",
                "status": "active",
                "role": "manager",
                "password": PASSWORD,
            },
        )
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()["resortIds"], [])
        new = User.objects.get(pk=result.json()["id"])
        self.api.force_login(new)
        self.assertEqual(self.api.get("/api/workspace").json()["resorts"], [])

    def test_accountant_cannot_own_resort_or_manage_accounts(self):
        accountant = User.objects.create_user(
            username="finance", email="finance@example.test", role="accountant", password=PASSWORD
        )
        self.assertEqual(
            self.write(
                "patch",
                f"/api/resorts/{self.resort.pk}",
                {"version": 1, "accountId": accountant.pk},
            ).status_code,
            422,
        )
        self.api.force_login(accountant)
        self.assertEqual(self.api.get("/api/clients").status_code, 403)

    def test_owner_role_cannot_change_to_accountant(self):
        result = self.write(
            "patch",
            f"/api/accounts/{self.manager.pk}",
            {
                "version": 1,
                "name": "Manager",
                "login": self.manager.email,
                "role": "accountant",
                "status": "active",
            },
        )
        self.assertEqual(result.status_code, 409, result.content)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.role, "manager")

    def test_directory_includes_guest_without_bookings_and_supports_search(self):
        guest_api = APIClient()
        guest = authenticate_guest(guest_api, name="Fictional directory guest")
        result = self.api.get("/api/clients", {"q": "Fictional directory"})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["count"], 1)
        item = result.json()["items"][0]
        self.assertEqual(item["bookingCount"], 0)
        self.assertEqual(item["account"]["status"], "active")
        self.assertNotIn("password", str(item))
        self.assertNotIn("owner", item["profile"])
        detail = self.api.get(f"/api/guests/{guest.profile_id}")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["bookings"], [])
        self.api.force_login(self.manager)
        self.assertEqual(self.api.get("/api/clients").status_code, 403)
        self.assertEqual(self.api.get(f"/api/guests/{guest.profile_id}").status_code, 404)

    def test_disable_guest_revokes_session_and_versions_changes_without_pii_audit(self):
        guest_api = APIClient()
        guest = authenticate_guest(guest_api)
        self.assertTrue(guest_api.get("/api/guest-auth/session").json()["authenticated"])
        url = f"/api/clients/{guest.profile_id}"
        self.assertEqual(
            self.api.patch(url, {"version": 1, "status": "disabled"}, format="json").status_code,
            403,
        )
        result = self.write("patch", url, {"version": 1, "status": "disabled"})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertFalse(guest_api.get("/api/guest-auth/session").json()["authenticated"])
        self.assertEqual(
            self.write("patch", url, {"version": 1, "status": "active"}).status_code, 409
        )
        self.assertEqual(
            self.write("patch", url, {"version": 2, "status": "active"}).status_code, 200
        )
        self.assertFalse(guest_api.get("/api/guest-auth/session").json()["authenticated"])
        self.assertNotIn(
            guest.phone, str(Audit.objects.filter(entity="guestAccounts").values("before", "after"))
        )
        self.assertTrue(GuestAccount.objects.get(pk=guest.pk).is_active)
