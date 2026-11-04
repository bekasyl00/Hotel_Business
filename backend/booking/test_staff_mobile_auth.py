import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth.hashers import make_password
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from identity.models import StaffDevice, StaffRefreshToken

from .authentication import token_hash
from .models import GuestAccount, GuestProfile, Resort, User
from .tests import PASSWORD, fixture


def login(user):
    return APIClient(enforce_csrf_checks=True).post(
        "/api/v1/staff-mobile-auth/login",
        {"email": user.email, "password": PASSWORD, "deviceName": "Test staff iPhone"},
        format="json",
    )


def bearer(token):
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    return client


def refresh(token):
    return APIClient(enforce_csrf_checks=True).post(
        "/api/v1/staff-mobile-auth/refresh", {"refreshToken": token}, format="json"
    )


class StaffMobileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.resort, cls.room, cls.tariff, cls.manager, cls.admin = fixture()
        cls.other = Resort.objects.create(name="Other", lat=42, lng=70)

    def session(self, user=None):
        response = login(user or self.manager)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_native_staff_has_no_cookie_and_server_scopes_workspace(self):
        response = login(self.manager)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("sessionid", response.cookies)
        self.assertIn("no-store", response["Cache-Control"])
        data = response.json()
        device = StaffDevice.objects.get(pk=data["deviceId"])
        self.assertEqual(device.access_hash, token_hash(data["accessToken"]))
        self.assertTrue(
            StaffRefreshToken.objects.filter(token_hash=token_hash(data["refreshToken"])).exists()
        )
        api = bearer(data["accessToken"])
        workspace = api.get("/api/v1/workspace")
        self.assertEqual(workspace.status_code, 200, workspace.content)
        self.assertEqual([r["id"] for r in workspace.json()["resorts"]], [self.resort.pk])
        self.assertEqual(workspace.json()["accounts"], [])
        self.assertEqual(api.get("/api/v1/auth/session").json()["id"], str(self.manager.pk))
        self.assertEqual(
            api.patch(
                f"/api/v1/resorts/{self.other.pk}", {"version": 1}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(api.post("/api/v1/accounts", {}, format="json").status_code, 403)
        administrator = bearer(self.session(self.admin)["accessToken"])
        self.assertEqual(len(administrator.get("/api/v1/workspace").json()["resorts"]), 2)

    def test_native_staff_order_requires_payment_instead_of_manual_confirmation(self):
        api = bearer(self.session()["accessToken"])
        start = timezone.localdate() + timedelta(days=8)
        response = api.post(
            "/api/v1/bookings",
            {
                "roomId": self.room.pk,
                "tariffId": self.tariff.pk,
                "start": str(start),
                "end": str(start + timedelta(days=2)),
                "guests": 1,
                "guestLabel": "Fictional Guest",
                "guestPhone": "+77000000000",
                "requestId": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        booking = response.json()
        self.assertEqual(booking["status"], "pending")
        response = api.patch(
            f"/api/v1/bookings/{booking['id']}",
            {"status": "confirmed", "version": booking["version"]},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        paid = api.post(
            "/api/v1/payments/demo/staff",
            {"bookingId": booking["id"], "requestId": str(uuid.uuid4()), "outcome": "success"},
            format="json",
        )
        self.assertEqual(paid.status_code, 200, paid.content)
        self.assertEqual(api.get("/api/v1/workspace").json()["bookings"][0]["status"], "confirmed")

    def test_guest_staff_and_django_admin_credentials_do_not_mix(self):
        account = GuestAccount.objects.create(
            phone="+77010000031",
            password=make_password(PASSWORD),
            profile=GuestProfile.objects.create(
                owner="guest-native-isolation", phone="+77010000031"
            ),
        )
        guest = (
            APIClient()
            .post(
                "/api/v1/mobile-auth/login",
                {"phone": account.phone, "password": PASSWORD, "deviceName": "Guest iPhone"},
                format="json",
            )
            .json()
        )
        client = bearer(guest["accessToken"])
        client.force_login(self.admin)
        self.assertEqual(client.get("/api/v1/workspace").status_code, 401)
        self.assertEqual(client.get("/api/v1/staff-mobile-auth/sessions").status_code, 401)
        staff = bearer(self.session()["accessToken"])
        self.assertEqual(staff.get("/api/v1/profile").status_code, 401)
        self.assertEqual(staff.get("/api/v1/mobile-auth/sessions").status_code, 401)
        self.assertEqual(
            staff.post(
                "/api/v1/mobile-auth/refresh",
                {"refreshToken": guest["refreshToken"]},
                format="json",
            ).status_code,
            401,
        )
        self.assertEqual(staff.get("/django-admin/").status_code, 302)
        self.assertEqual(refresh(guest["refreshToken"]).status_code, 401)
        client.credentials(HTTP_AUTHORIZATION="Bearer broken")
        self.assertEqual(client.get("/api/v1/workspace").status_code, 401)

    def test_rotation_invalidates_old_access_and_replay_revokes_family(self):
        old = self.session()
        rotated = refresh(old["refreshToken"])
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(bearer(old["accessToken"]).get("/api/workspace").status_code, 401)
        self.assertEqual(
            bearer(rotated.json()["accessToken"]).get("/api/workspace").status_code, 200
        )
        self.assertEqual(refresh(old["refreshToken"]).status_code, 401)
        self.assertEqual(
            bearer(rotated.json()["accessToken"]).get("/api/workspace").status_code, 401
        )

    def test_password_role_resort_and_deactivation_revoke_credentials(self):
        for change in ["password", "role", "resort", "is_active"]:
            with self.subTest(change=change):
                user = User.objects.get(pk=self.manager.pk)
                session = self.session(user)
                if change == "password":
                    user.set_password("new-different-password-9901")
                elif change == "role":
                    user.role = "admin"
                elif change == "resort":
                    user.resort = self.other
                else:
                    user.is_active = False
                user.save()
                self.assertEqual(
                    bearer(session["accessToken"]).get("/api/workspace").status_code, 401
                )
                self.assertEqual(refresh(session["refreshToken"]).status_code, 401)
                user.set_password(PASSWORD)
                user.role, user.resort, user.is_active = "manager", self.resort, True
                user.save()

    def test_device_revocation_logout_and_expiry(self):
        first, second, foreign = self.session(), self.session(), self.session(self.admin)
        api = bearer(first["accessToken"])
        listed = api.get("/api/v1/staff-mobile-auth/sessions").json()["sessions"]
        self.assertEqual(len(listed), 2)
        self.assertEqual(
            api.delete("/api/v1/staff-mobile-auth/sessions/" + foreign["deviceId"]).status_code, 404
        )
        self.assertEqual(
            api.delete("/api/v1/staff-mobile-auth/sessions/" + second["deviceId"]).status_code, 204
        )
        self.assertEqual(refresh(second["refreshToken"]).status_code, 401)
        self.assertEqual(
            api.post("/api/v1/staff-mobile-auth/logout", {}, format="json").status_code, 204
        )
        self.assertEqual(api.get("/api/workspace").status_code, 401)
        StaffDevice.objects.filter(pk=foreign["deviceId"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(refresh(foreign["refreshToken"]).status_code, 401)


class StaffRefreshConcurrencyTests(TransactionTestCase):
    def test_concurrent_refresh_is_one_success_and_replay_revocation(self):
        _, _, _, manager, _ = fixture()
        token = login(manager).json()["refreshToken"]
        barrier = Barrier(2)

        def attempt():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = refresh(token)
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sorted(status for status, _ in results), [200, 401])
        access = next(data["accessToken"] for status, data in results if status == 200)
        self.assertEqual(bearer(access).get("/api/workspace").status_code, 401)
