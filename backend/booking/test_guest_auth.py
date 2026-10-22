import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace

from django.contrib.auth.hashers import check_password
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from commerce.models import DemoPayment

from .errors import Problem
from .guest_auth import register
from .models import Audit, Booking, GuestAccount, GuestChallenge, GuestProfile, LoginAttempt
from .tests import PASSWORD, fixture

PHONE = "+77010000001"
NEW_PASSWORD = "Replacement-forest-93845!"


def client():
    return APIClient(enforce_csrf_checks=True)


def write(api, action, data=None):
    token = api.get("/api/auth/csrf").json()["token"]
    return api.post(
        "/api/guest-auth/" + action,
        data or {},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )


def challenge(api, phone=PHONE, purpose="register"):
    response = write(api, "challenges", {"phone": phone, "purpose": purpose})
    assert response.status_code == 200, response.content
    return response.json()


def register_client(api, phone=PHONE, name="Тестовый гость"):
    item = challenge(api, phone)
    response = write(
        api,
        "register",
        {
            "challengeId": item["challengeId"],
            "code": item["demoCode"],
            "name": name,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.content
    return response.json()


@override_settings(DEBUG=True, GUEST_AUTH_DEMO_OTP=True)
class GuestAuthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.resort, cls.room, cls.tariff, cls.manager, cls.admin = fixture()

    def booking(self, api, offset=1):
        start = timezone.localdate() + timedelta(days=offset)
        token = api.get("/api/auth/csrf").json()["token"]
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
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Booking.objects.get(pk=response.json()["id"])

    def test_registration_adopts_only_current_history_and_rotates_opaque_owner(self):
        api = client()
        booking = self.booking(api)
        old_owner, old_profile = booking.owner, booking.guest_profile_id
        old_cookie = api.cookies["sessionid"].value
        stale = client()
        stale.cookies["sessionid"] = old_cookie
        result = register_client(api, phone="8 (701) 000-00-01")
        booking.refresh_from_db()
        self.assertNotEqual(booking.owner, old_owner)
        self.assertEqual(booking.guest_profile_id, old_profile)
        self.assertEqual(result["profile"]["id"], old_profile)
        self.assertEqual(result["account"]["phone"], PHONE)
        self.assertNotEqual(api.cookies["sessionid"].value, old_cookie)
        self.assertEqual(stale.get("/api/my-bookings").json(), [])
        self.assertEqual(api.get("/api/my-bookings").json()[0]["id"], booking.pk)
        self.assertEqual(api.get("/api/workspace").status_code, 401)
        self.assertEqual(api.get("/api/auth/session").status_code, 204)
        account = GuestAccount.objects.get()
        self.assertTrue(check_password(PASSWORD, account.password))
        otp = GuestChallenge.objects.get()
        self.assertNotEqual(otp.code_hash, "000000")
        self.assertTrue(otp.code_hash.startswith("pbkdf2_"))
        self.assertIsNotNone(otp.consumed_at)
        self.assertNotIn(PHONE, str(list(Audit.objects.filter(entity="guestAccounts").values())))
        self.assertNotIn("password", result)

    def test_cross_device_login_does_not_merge_phone_or_previous_browser_history(self):
        first = client()
        own = self.booking(first)
        identity = register_client(first)
        second = client()
        unrelated = self.booking(second, offset=5)
        self.assertEqual(GuestProfile.objects.filter(phone=PHONE).count(), 2)
        result = write(second, "login", {"phone": PHONE, "password": PASSWORD})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["account"]["id"], identity["account"]["id"])
        self.assertEqual([b["id"] for b in second.get("/api/my-bookings").json()], [own.id])
        unrelated.refresh_from_db()
        self.assertNotEqual(unrelated.guest_profile_id, own.guest_profile_id)
        self.assertEqual(write(second, "logout").status_code, 200)
        self.assertFalse(second.get("/api/guest-auth/session").json()["authenticated"])
        self.assertEqual(second.get("/api/my-bookings").json(), [])
        self.assertTrue(first.get("/api/guest-auth/session").json()["authenticated"])

    def test_account_switch_and_guest_logout_do_not_grant_or_remove_staff_role(self):
        first = client()
        one = register_client(first)
        second = client()
        two = register_client(second, phone="+77010000002")
        second.force_login(self.manager)
        response = write(second, "login", {"phone": PHONE, "password": PASSWORD})
        self.assertEqual(response.json()["account"]["id"], one["account"]["id"])
        self.assertNotEqual(response.json()["profile"]["id"], two["profile"]["id"])
        self.assertEqual(second.get("/api/workspace").status_code, 200)
        write(second, "logout")
        self.assertEqual(second.get("/api/workspace").status_code, 200)
        self.assertIsNone(second.get("/api/guest-auth/session").json()["account"])

    def test_verified_profile_phone_cannot_change_without_a_new_verification_flow(self):
        api = client()
        identity = register_client(api)
        token = api.get("/api/auth/csrf").json()["token"]
        response = api.patch(
            "/api/profile",
            {"name": "Новое имя", "phone": "+77010000002"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "phone_change_requires_verification")
        response = api.patch(
            "/api/profile",
            {"name": "Новое имя", "phone": "8 (701) 000-00-01"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["profile"]["phone"], PHONE)
        from .services import upsert_guest_profile

        account = GuestAccount.objects.get(pk=identity["account"]["id"])
        upsert_guest_profile(account.profile.owner, "Имя из брони", "+77010000003")
        self.assertEqual(api.get("/api/profile").json()["profile"]["phone"], PHONE)
        account.refresh_from_db()
        self.assertEqual(account.phone, PHONE)

    def test_reset_revokes_every_guest_session_including_receipt_and_payment_access(self):
        first, second, recovery = client(), client(), client()
        booking = self.booking(first)
        register_client(first)
        self.assertEqual(
            write(second, "login", {"phone": PHONE, "password": PASSWORD}).status_code, 200
        )
        booking.refresh_from_db()
        booking.status = "confirmed"
        booking.save(update_fields=["status"])
        payment = DemoPayment.objects.create(
            booking=booking,
            request_key=uuid.uuid4(),
            outcome="success",
            status="paid",
            amount=booking.snapshot["total"],
        )
        receipt_url = f"/api/receipts/{payment.pk}"
        self.assertEqual(second.get(receipt_url).status_code, 200)
        item = challenge(recovery, purpose="reset")
        result = write(
            recovery,
            "reset",
            {
                "challengeId": item["challengeId"],
                "code": item["demoCode"],
                "password": NEW_PASSWORD,
            },
        )
        self.assertEqual(result.json(), {"ok": True, "mode": "demo"})
        for api in [first, second]:
            self.assertEqual(api.get(receipt_url).status_code, 404)
            self.assertEqual(api.get("/api/my-bookings").json(), [])
            self.assertFalse(api.get("/api/guest-auth/session").json()["authenticated"])
            token = api.get("/api/auth/csrf").json()["token"]
            denied = api.post(
                "/api/payments/demo",
                {"bookingId": booking.id, "requestId": str(uuid.uuid4()), "outcome": "success"},
                format="json",
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(denied.status_code, 404)
        self.assertEqual(
            write(first, "login", {"phone": PHONE, "password": PASSWORD}).status_code, 401
        )
        self.assertEqual(
            write(first, "login", {"phone": PHONE, "password": NEW_PASSWORD}).status_code, 200
        )
        self.assertEqual(first.get(receipt_url).status_code, 200)
        self.assertEqual(GuestAccount.objects.get().auth_version, 2)
        unknown = challenge(recovery, phone="+77010000003", purpose="reset")
        result_unknown = write(
            recovery,
            "reset",
            {
                "challengeId": unknown["challengeId"],
                "code": unknown["demoCode"],
                "password": NEW_PASSWORD,
            },
        )
        self.assertEqual(result_unknown.json(), result.json())
        self.assertEqual(set(unknown), set(item))

    def test_code_attempts_expiry_single_use_and_browser_binding(self):
        api = client()
        item = challenge(api)
        data = {
            "challengeId": item["challengeId"],
            "code": item["demoCode"],
            "name": "Гость",
            "password": PASSWORD,
        }
        self.assertEqual(write(client(), "register", data).status_code, 422)
        wrong = "111111" if item["demoCode"] != "111111" else "222222"
        for _ in range(5):
            self.assertEqual(
                write(api, "register", {**data, "code": wrong}).json()["code"], "invalid_code"
            )
        self.assertEqual(GuestChallenge.objects.get(pk=item["challengeId"]).attempts, 5)
        self.assertEqual(write(api, "register", data).status_code, 422)
        self.assertEqual(GuestAccount.objects.count(), 0)
        item = challenge(api, phone="+77010000002")
        data.update(challengeId=item["challengeId"], code=item["demoCode"])
        GuestChallenge.objects.filter(pk=item["challengeId"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(write(api, "register", data).json()["code"], "code_expired")
        GuestChallenge.objects.filter(pk=item["challengeId"]).update(
            expires_at=timezone.now() + timedelta(minutes=1)
        )
        self.assertEqual(write(api, "register", data).status_code, 201)
        write(api, "logout")
        self.assertEqual(write(api, "register", data).status_code, 422)

    def test_resend_cooldown_invalidates_old_code_and_normalizes_phone(self):
        api = client()
        one = challenge(api, phone="8 701 000 00 01")
        response = write(api, "challenges", {"phone": PHONE, "purpose": "register"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "resend_cooldown")
        GuestChallenge.objects.filter(pk=one["challengeId"]).update(
            created_at=timezone.now() - timedelta(seconds=61)
        )
        two = challenge(api)
        self.assertIsNotNone(GuestChallenge.objects.get(pk=one["challengeId"]).consumed_at)
        self.assertEqual(
            write(
                api,
                "register",
                {
                    "challengeId": one["challengeId"],
                    "code": one["demoCode"],
                    "name": "Гость",
                    "password": PASSWORD,
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            write(
                api,
                "register",
                {
                    "challengeId": two["challengeId"],
                    "code": two["demoCode"],
                    "name": "Гость",
                    "password": PASSWORD,
                },
            ).status_code,
            201,
        )

    def test_sms_disabled_fails_closed_even_for_previously_issued_code(self):
        api = client()
        item = challenge(api)
        for override in [
            {"GUEST_AUTH_DEMO_OTP": False},
            {"DEBUG": False, "SECURE_SSL_REDIRECT": False},
        ]:
            with self.settings(**override):
                for action, data in [
                    ("challenges", {"phone": PHONE, "purpose": "reset"}),
                    (
                        "register",
                        {
                            "challengeId": item["challengeId"],
                            "code": item["demoCode"],
                            "name": "Гость",
                            "password": PASSWORD,
                        },
                    ),
                    (
                        "reset",
                        {
                            "challengeId": item["challengeId"],
                            "code": item["demoCode"],
                            "password": PASSWORD,
                        },
                    ),
                ]:
                    response = write(api, action, data)
                    self.assertEqual(response.status_code, 503, response.content)
                    self.assertEqual(response.json()["code"], "sms_unavailable")
                    self.assertNotIn("demoCode", response.json())
        self.assertEqual(GuestAccount.objects.count(), 0)

    def test_csrf_is_required_and_rotated_at_registration(self):
        api = client()
        old_token = api.get("/api/auth/csrf").json()["token"]
        for action in ["challenges", "register", "login", "reset", "logout"]:
            self.assertEqual(
                api.post("/api/guest-auth/" + action, {}, format="json").status_code, 403
            )
        register_client(api)
        self.assertEqual(
            api.post(
                "/api/guest-auth/logout", {}, format="json", HTTP_X_CSRFTOKEN=old_token
            ).status_code,
            403,
        )
        self.assertIn("no-store", api.get("/api/guest-auth/session")["Cache-Control"])
        self.assertEqual(write(api, "logout").status_code, 200)

    def test_input_validation_and_shared_rate_limit_preserve_machine_codes(self):
        api = client()
        for phone in [PHONE + "0", "+79010000001", "javascript:alert(1)", 77010000001]:
            response = write(api, "challenges", {"phone": phone, "purpose": "register"})
            self.assertEqual(response.json()["code"], "phone_invalid")
        item = challenge(api)
        data = {
            "challengeId": item["challengeId"],
            "code": item["demoCode"],
            "name": "Гость",
            "password": "123456789012",
        }
        self.assertEqual(write(api, "register", data).json()["code"], "weak_password")
        self.assertEqual(
            write(api, "register", {**data, "role": "admin"}).json()["code"], "invalid_request"
        )
        self.assertEqual(GuestChallenge.objects.get(pk=item["challengeId"]).attempts, 0)
        # Shared PostgreSQL counters limit the same phone from another browser too.
        for _ in range(10):
            self.assertEqual(
                write(api, "login", {"phone": PHONE, "password": "wrong"}).status_code, 401
            )
        response = write(client(), "login", {"phone": PHONE, "password": "wrong"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "rate_limited")


@override_settings(DEBUG=True, GUEST_AUTH_DEMO_OTP=True)
class GuestAuthConcurrencyTests(TransactionTestCase):
    def test_a_single_challenge_cannot_create_two_accounts_under_concurrency(self):
        api = client()
        item = challenge(api)
        session_key = api.cookies["sessionid"].value
        data = {
            "challengeId": item["challengeId"],
            "code": item["demoCode"],
            "name": "Гость",
            "password": PASSWORD,
        }
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            session = SessionStore(session_key=session_key)
            dict(session.items())
            request = SimpleNamespace(data=data, session=session, META={"REMOTE_ADDR": "test"})
            barrier.wait()
            try:
                register(request)
                return "created"
            except Problem as exc:
                return exc.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertCountEqual(results, ["created", 422])
        self.assertEqual(GuestAccount.objects.count(), 1)
        self.assertEqual(Audit.objects.filter(action="register").count(), 1)
        self.assertEqual(GuestChallenge.objects.filter(consumed_at__isnull=False).count(), 1)
        self.assertGreater(LoginAttempt.objects.count(), 0)
