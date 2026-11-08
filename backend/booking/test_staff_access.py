from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Audit, User
from .test_staff_mobile_auth import bearer, refresh
from .test_staff_mobile_auth import login as native_login
from .tests import PASSWORD, fixture


class StaffAccessTests(TestCase):
    def setUp(self):
        self.resort, self.room, _, self.manager, self.admin = fixture()
        self.accountant = User.objects.create_user(
            username="finance@example.test",
            email="finance@example.test",
            role="accountant",
            password=PASSWORD,
        )
        self.admin_api = APIClient(enforce_csrf_checks=True)
        self.admin_api.force_login(self.admin)
        self.csrf = self.admin_api.get("/api/auth/csrf").json()["token"]

    def account_patch(self, **changes):
        payload = {
            "version": self.manager.version,
            "name": self.manager.name,
            "login": self.manager.email,
            "role": "manager",
            "status": "active",
            **changes,
        }
        return self.admin_api.patch(
            f"/api/accounts/{self.manager.pk}",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )

    def browser_login(self, api, email):
        csrf = api.get("/api/auth/csrf").json()["token"]
        return api.post(
            "/api/auth/login",
            {"email": email, "password": PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

    def test_audit_only_platform_admin_for_browser_and_native(self):
        event = Audit.objects.create(
            actor="Test admin",
            resort=self.resort,
            entity="rooms",
            entity_id=self.room.pk,
            action="update",
            label="Internal change",
            before={"price": 18000},
            after={"price": 19000},
        )
        for user in (self.admin, self.manager, self.accountant):
            cookie = APIClient()
            cookie.force_login(user)
            clients = [cookie]
            if user.role != "accountant":
                native_response = native_login(user)
                self.assertEqual(native_response.status_code, 200, native_response.content)
                clients.append(bearer(native_response.json()["accessToken"]))
            expected_events = list(Audit.objects.order_by("-at").values_list("pk", flat=True))
            for api in clients:
                with self.subTest(role=user.role, transport=api is cookie):
                    response = api.get("/api/v1/workspace")
                    self.assertEqual(response.status_code, 200, response.content)
                    self.assertEqual(
                        [entry["id"] for entry in response.json()["audit"]],
                        expected_events if user.role == "admin" else [],
                    )
                    self.assertEqual(len(response.json()["rooms"]), 1)
        self.assertTrue(Audit.objects.filter(pk=event.pk).exists())
        self.assertEqual(APIClient().get("/api/v1/workspace").status_code, 401)

    def test_admin_email_edit_normalizes_preserves_identity_and_revokes_sessions(self):
        browser = APIClient(enforce_csrf_checks=True)
        old_email = self.manager.email
        self.assertEqual(self.browser_login(browser, old_email).status_code, 200)
        native = native_login(self.manager).json()
        original_password = self.manager.password
        response = self.account_patch(login="  New.Manager@Example.Test  ")
        self.assertEqual(response.status_code, 200, response.content)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.email, "new.manager@example.test")
        self.assertEqual(self.manager.username, self.manager.email)
        self.assertEqual(self.manager.version, 2)
        self.assertEqual(self.manager.password, original_password)
        self.assertEqual(self.resort.account_id, self.manager.pk)
        self.assertEqual(response.json()["id"], str(self.manager.pk))
        self.assertEqual(response.json()["resortIds"], [self.resort.pk])
        self.assertEqual(browser.get("/api/workspace").status_code, 401)
        self.assertEqual(browser.get("/api/auth/session").status_code, 204)
        self.assertEqual(bearer(native["accessToken"]).get("/api/workspace").status_code, 401)
        self.assertEqual(refresh(native["refreshToken"]).status_code, 401)
        self.assertEqual(self.browser_login(browser, old_email).status_code, 401)
        self.assertEqual(self.browser_login(browser, " NEW.MANAGER@example.test ").status_code, 200)
        self.assertEqual(browser.get("/api/workspace").status_code, 200)
        self.assertEqual(native_login(self.manager).status_code, 200)
        self.assertEqual(self.admin_api.get("/api/workspace").status_code, 200)

    def test_email_validation_uniqueness_and_stale_edits_preserve_account(self):
        # Legacy username can differ from email; both database uniqueness rules must be checked.
        User.objects.create_user(
            username="reserved@example.test", email="different@example.test", password=PASSWORD
        )
        for email in ("FINANCE@example.test", "RESERVED@example.test", "invalid-address"):
            with self.subTest(email=email):
                response = self.account_patch(login=email)
                self.assertEqual(response.status_code, 422, response.content)
                self.manager.refresh_from_db()
                self.assertEqual(self.manager.email, "manager@example.test")
                self.assertEqual(self.manager.version, 1)
        response = self.account_patch(login="changed@example.test")
        self.assertEqual(response.status_code, 200, response.content)
        stale = self.account_patch(login="stale@example.test")
        self.assertEqual(stale.status_code, 409, stale.content)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.email, "changed@example.test")
        self.assertEqual(Audit.objects.filter(entity="accounts").count(), 1)

    def test_manager_and_accountant_cannot_edit_staff_email(self):
        for user in (self.manager, self.accountant):
            with self.subTest(role=user.role):
                self.admin_api.force_login(user)
                self.csrf = self.admin_api.get("/api/auth/csrf").json()["token"]
                response = self.account_patch(login="forbidden@example.test")
                self.assertEqual(response.status_code, 403, response.content)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.email, "manager@example.test")
        self.assertEqual(self.manager.version, 1)

    def test_session_hash_supports_secret_rotation_and_changes_with_credential_version(self):
        with override_settings(SECRET_KEY="new-key", SECRET_KEY_FALLBACKS=["old-key"]):
            fallback = list(self.manager.get_session_auth_fallback_hash())
            with override_settings(SECRET_KEY="old-key"):
                self.assertEqual(fallback, [self.manager.get_session_auth_hash()])
        before = self.manager.get_session_auth_hash()
        self.manager.version += 1
        self.assertNotEqual(before, self.manager.get_session_auth_hash())
