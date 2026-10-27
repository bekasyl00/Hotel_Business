import io
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from identity.models import GuestDevice, GuestRefreshToken

from .authentication import GuestTokenContext, token_hash
from .mobile_auth import revoke_session
from .models import Booking, GuestAccount, GuestProfile
from .test_guest_auth import NEW_PASSWORD, challenge, write
from .tests import PASSWORD, fixture

PHONE = "+77010000021"


@override_settings(DEBUG=True, GUEST_AUTH_DEMO_OTP=True)
class MobileAuthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.resort, cls.room, cls.tariff, cls.manager, cls.admin = fixture()
        cls.profile = GuestProfile.objects.create(
            owner="mobile-owner-a", name="Тестовый гость", phone=PHONE
        )
        cls.account = GuestAccount.objects.create(
            profile=cls.profile, phone=PHONE, password=make_password(PASSWORD)
        )
        cls.other = GuestAccount.objects.create(
            profile=GuestProfile.objects.create(
                owner="mobile-owner-b", name="Другой гость", phone="+77010000022"
            ),
            phone="+77010000022",
            password=make_password(PASSWORD),
        )

    def login(self, phone=PHONE, name="Test iPhone", api=None):
        api = api or APIClient(enforce_csrf_checks=True)
        response = api.post(
            "/api/mobile-auth/login",
            {
                "phone": phone,
                "password": PASSWORD,
                "deviceName": name,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("no-store", response["Cache-Control"])
        return response.json()

    def bearer(self, value):
        api = APIClient(enforce_csrf_checks=True)
        api.credentials(HTTP_AUTHORIZATION="Bearer " + value)
        return api

    def refresh(self, value):
        return APIClient(enforce_csrf_checks=True).post(
            "/api/mobile-auth/refresh", {"refreshToken": value}, format="json"
        )

    def test_login_uses_hashed_tokens_and_does_not_create_cookie_session(self):
        api = APIClient(enforce_csrf_checks=True)
        result = self.login(api=api)
        self.assertNotIn("sessionid", api.cookies)
        self.assertEqual(result["expiresIn"], 900)
        self.assertEqual(result["profile"]["id"], self.profile.pk)
        device = GuestDevice.objects.get(pk=result["deviceId"])
        self.assertEqual(device.access_hash, token_hash(result["accessToken"]))
        self.assertNotEqual(device.access_hash, result["accessToken"])
        self.assertTrue(
            GuestRefreshToken.objects.filter(
                token_hash=token_hash(result["refreshToken"]), device=device
            ).exists()
        )

    def test_mobile_uses_same_profile_and_guest_bookings_but_never_staff(self):
        result = self.login()
        api = self.bearer(result["accessToken"])
        profile = api.get("/api/profile")
        self.assertEqual(profile.status_code, 200, profile.content)
        self.assertEqual(profile.json()["profile"]["id"], self.profile.pk)
        self.assertEqual(api.get("/api/workspace").status_code, 401)
        start = timezone.localdate() + timedelta(days=6)
        response = api.post(
            "/api/my-bookings",
            {
                "roomId": self.room.pk,
                "tariffId": self.tariff.pk,
                "start": str(start),
                "end": str(start + timedelta(days=2)),
                "guests": 1,
                "guestLabel": "Тестовый гость",
                "guestPhone": PHONE,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        booking = Booking.objects.get(pk=response.json()["id"])
        self.assertEqual(booking.owner, self.profile.owner)
        self.assertEqual(booking.status, "pending")
        web = APIClient(enforce_csrf_checks=True)
        signed_in = write(web, "login", {"phone": PHONE, "password": PASSWORD})
        self.assertEqual(signed_in.status_code, 200, signed_in.content)
        self.assertEqual(web.get("/api/my-bookings").json()[0]["id"], booking.pk)
        other_api = self.bearer(self.login(phone=self.other.phone)["accessToken"])
        self.assertEqual(other_api.get("/api/my-bookings").json(), [])
        booking.status = "confirmed"
        booking.save(update_fields=["status"])
        payment = api.post(
            "/api/payments/demo",
            {
                "bookingId": booking.pk,
                "requestId": str(uuid.uuid4()),
                "outcome": "success",
            },
            format="json",
        )
        self.assertEqual(payment.status_code, 200, payment.content)
        receipt_path = "/api/receipts/" + payment.json()["id"]
        self.assertEqual(api.get(receipt_path).status_code, 200)
        self.assertEqual(other_api.get(receipt_path).status_code, 404)
        self.assertEqual(api.get("/api/cancellation-preview/" + booking.pk).status_code, 200)
        self.assertEqual(other_api.get("/api/cancellation-preview/" + booking.pk).status_code, 404)

    def test_invalid_bearer_fails_closed_and_cannot_fall_back_to_staff_cookie(self):
        api = APIClient(enforce_csrf_checks=True)
        api.force_login(self.admin)
        api.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assertEqual(api.get("/api/workspace").status_code, 401)
        response = api.post("/api/my-bookings", {}, format="json")
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(response.json()["code"], "invalid_token")
        api.credentials(HTTP_AUTHORIZATION="Bearer " + self.login()["accessToken"])
        self.assertEqual(api.get("/api/workspace").status_code, 401)

    def test_web_mutations_still_require_csrf(self):
        api = APIClient(enforce_csrf_checks=True)
        self.assertEqual(api.post("/api/my-bookings", {}, format="json").status_code, 403)
        self.assertEqual(api.post("/api/payments/demo", {}, format="json").status_code, 403)
        self.assertEqual(
            api.post(
                "/api/guest-auth/login",
                {
                    "phone": PHONE,
                    "password": PASSWORD,
                },
                format="json",
            ).status_code,
            403,
        )

    def test_refresh_rotates_and_replay_revokes_entire_family_only(self):
        initial = self.login()
        second_device = self.login(name="Second device")
        refreshed = self.refresh(initial["refreshToken"])
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        current = refreshed.json()
        self.assertNotEqual(current["accessToken"], initial["accessToken"])
        self.assertNotEqual(current["refreshToken"], initial["refreshToken"])
        self.assertEqual(self.bearer(initial["accessToken"]).get("/api/profile").status_code, 401)
        self.assertEqual(self.bearer(current["accessToken"]).get("/api/profile").status_code, 200)
        replay = self.refresh(initial["refreshToken"])
        self.assertEqual(replay.status_code, 401, replay.content)
        self.assertEqual(self.bearer(current["accessToken"]).get("/api/profile").status_code, 401)
        self.assertEqual(self.refresh(current["refreshToken"]).status_code, 401)
        self.assertEqual(
            self.bearer(second_device["accessToken"]).get("/api/profile").status_code, 200
        )

    def test_access_expiry_allows_refresh_but_family_expiry_does_not(self):
        result = self.login()
        GuestDevice.objects.filter(pk=result["deviceId"]).update(
            access_expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.bearer(result["accessToken"]).get("/api/profile").status_code, 401)
        refreshed = self.refresh(result["refreshToken"])
        self.assertEqual(refreshed.status_code, 200)
        GuestDevice.objects.filter(pk=result["deviceId"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.refresh(refreshed.json()["refreshToken"]).status_code, 401)

    def test_reset_revokes_native_access_and_refresh(self):
        result = self.login()
        web = APIClient(enforce_csrf_checks=True)
        item = challenge(web, phone=PHONE, purpose="reset")
        response = write(
            web,
            "reset",
            {
                "challengeId": item["challengeId"],
                "code": item["demoCode"],
                "password": NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.bearer(result["accessToken"]).get("/api/profile").status_code, 401)
        self.assertEqual(self.refresh(result["refreshToken"]).status_code, 401)

    def test_device_list_revoke_and_logout_are_owner_scoped(self):
        initial, second = self.login(), self.login(name="Tablet")
        foreign = self.login(phone=self.other.phone)
        api = self.bearer(initial["accessToken"])
        sessions = api.get("/api/mobile-auth/sessions").json()["sessions"]
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sum(s["current"] for s in sessions), 1)
        self.assertNotIn("access_hash", str(sessions))
        self.assertEqual(
            api.delete("/api/mobile-auth/sessions/" + foreign["deviceId"]).status_code, 404
        )
        self.assertEqual(
            api.delete("/api/mobile-auth/sessions/" + second["deviceId"]).status_code, 204
        )
        self.assertEqual(self.bearer(second["accessToken"]).get("/api/profile").status_code, 401)
        self.assertEqual(api.post("/api/mobile-auth/logout", {}, format="json").status_code, 204)
        self.assertEqual(api.get("/api/profile").status_code, 401)
        self.assertEqual(self.refresh(initial["refreshToken"]).status_code, 401)

    def test_native_login_does_not_trust_web_cookie_or_form_data(self):
        api = APIClient(enforce_csrf_checks=True)
        api.force_login(self.admin)
        response = api.post(
            "/api/mobile-auth/login",
            {
                "phone": PHONE,
                "password": "wrong",
                "deviceName": "Test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(api.get("/api/mobile-auth/sessions").status_code, 401)
        response = api.post(
            "/api/mobile-auth/login",
            {
                "phone": PHONE,
                "password": PASSWORD,
                "deviceName": "Test",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 415)

    def test_avatar_upload_and_download_use_bearer_owner_even_with_staff_cookie(self):
        account_a = self.login()
        api = self.bearer(account_a["accessToken"])
        image = io.BytesIO()
        Image.new("RGB", (12, 12), "blue").save(image, "PNG")
        with tempfile.TemporaryDirectory() as media_dir, override_settings(MEDIA_ROOT=media_dir):
            response = api.post(
                "/api/profile/avatar",
                {
                    "file": SimpleUploadedFile(
                        "portrait.png", image.getvalue(), content_type="image/png"
                    ),
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 200, response.content)
            url = response.json()["profile"]["avatarUrl"]
            result = api.get(url)
            self.assertEqual(result.status_code, 200)
            self.assertTrue(b"".join(result.streaming_content).startswith(b"\xff\xd8"))
            foreign = self.bearer(self.login(phone=self.other.phone)["accessToken"])
            foreign.force_login(self.admin)
            denied = foreign.get(url)
            self.assertEqual(denied.status_code, 404)
            self.assertEqual(api.delete("/api/profile/avatar").status_code, 200)
            self.assertEqual(api.get(url).status_code, 404)


class MobileRefreshConcurrencyTests(TransactionTestCase):
    def setUp(self):
        profile = GuestProfile.objects.create(owner="concurrent-native", name="Guest", phone=PHONE)
        GuestAccount.objects.create(profile=profile, phone=PHONE, password=make_password(PASSWORD))
        login = APIClient(enforce_csrf_checks=True).post(
            "/api/mobile-auth/login",
            {
                "phone": PHONE,
                "password": PASSWORD,
                "deviceName": "Test device",
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.content)
        self.original = login.json()

    def test_simultaneous_refresh_reuse_is_detected_and_revocation_persists(self):
        original = self.original
        barrier = Barrier(2)

        def refresh_same_token():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = APIClient(enforce_csrf_checks=True).post(
                    "/api/mobile-auth/refresh",
                    {"refreshToken": original["refreshToken"]},
                    format="json",
                )
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(refresh_same_token) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(status for status, _ in results), [200, 401])
        fresh = next(data for status, data in results if status == 200)
        api = APIClient(enforce_csrf_checks=True)
        api.credentials(HTTP_AUTHORIZATION="Bearer " + fresh["accessToken"])
        self.assertEqual(api.get("/api/profile").status_code, 401)
        self.assertIsNotNone(GuestDevice.objects.get(pk=original["deviceId"]).revoked_at)

    def test_refresh_and_already_authenticated_device_revoke_cannot_resurrect_session(self):
        original = self.original
        context = GuestTokenContext(
            GuestDevice.objects.select_related("account").get(pk=original["deviceId"])
        )
        barrier = Barrier(2)

        def refresh_token():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = APIClient(enforce_csrf_checks=True).post(
                    "/api/mobile-auth/refresh",
                    {
                        "refreshToken": original["refreshToken"],
                    },
                    format="json",
                )
                return response.status_code, response.json()
            finally:
                connections.close_all()

        def revoke_device():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                revoke_session(context, context.device.pk, "native_logout")
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            refresh_future = pool.submit(refresh_token)
            revoke_future = pool.submit(revoke_device)
            status, data = refresh_future.result(timeout=20)
            revoke_future.result(timeout=20)
        self.assertIn(status, [200, 401])
        self.assertIsNotNone(GuestDevice.objects.get(pk=original["deviceId"]).revoked_at)
        if status == 200:
            api = APIClient(enforce_csrf_checks=True)
            api.credentials(HTTP_AUTHORIZATION="Bearer " + data["accessToken"])
            self.assertEqual(api.get("/api/profile").status_code, 401)
