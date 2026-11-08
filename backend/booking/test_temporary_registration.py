from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth.hashers import check_password
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .guest_auth import digest
from .models import Audit, GuestAccount, GuestChallenge, GuestProfile, LoginAttempt
from .test_guest_auth import PHONE, client, write

SIGNUP = {"phone": PHONE, "name": "Временный гость", "password": "12345678"}
TEMPORARY = {
    "DEBUG": False,
    "SECURE_SSL_REDIRECT": False,
    "GUEST_AUTH_DEMO_OTP": False,
    "GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION": True,
}


@override_settings(**TEMPORARY)
class TemporaryRegistrationTests(TestCase):
    def test_registration_and_password_login_work_without_sms_and_do_not_claim_verification(self):
        api = client()
        session = api.get("/api/guest-auth/session").json()
        self.assertEqual(session["registrationMode"], "password")
        self.assertFalse(session["passwordResetAvailable"])
        old_token = api.get("/api/auth/csrf").json()["token"]
        response = write(api, "register", SIGNUP)
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertTrue(data["authenticated"])
        self.assertFalse(data["account"]["phoneVerified"])
        account = GuestAccount.objects.get()
        self.assertTrue(check_password(SIGNUP["password"], account.password))
        self.assertIsNone(account.phone_verified_at)
        self.assertEqual(GuestChallenge.objects.count(), 0)
        self.assertNotIn("demoCode", data)
        self.assertNotIn(PHONE, str(list(Audit.objects.values())))
        self.assertEqual(
            api.post(
                "/api/guest-auth/logout", {}, format="json", HTTP_X_CSRFTOKEN=old_token
            ).status_code,
            403,
        )
        second = client()
        self.assertEqual(
            write(second, "login", {"phone": PHONE, "password": SIGNUP["password"]}).status_code,
            200,
        )
        self.assertEqual(second.get("/api/workspace").status_code, 401)
        self.assertFalse(second.get("/api/guest-auth/session").json()["account"]["phoneVerified"])

    def test_feature_off_does_not_bypass_challenge_and_existing_login_survives_switch_off(self):
        api = client()
        self.assertEqual(write(api, "register", SIGNUP).status_code, 201)
        with self.settings(GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION=False):
            other = client()
            self.assertEqual(
                other.get("/api/guest-auth/session").json()["registrationMode"], "disabled"
            )
            response = write(other, "register", {**SIGNUP, "phone": "+77010000002"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["code"], "sms_unavailable")
            self.assertEqual(
                write(other, "login", {"phone": PHONE, "password": SIGNUP["password"]}).status_code,
                200,
            )
        self.assertEqual(GuestAccount.objects.count(), 1)

    def test_existing_number_cannot_be_replaced_or_merged(self):
        one, two = client(), client()
        self.assertEqual(write(one, "register", SIGNUP).status_code, 201)
        original = GuestAccount.objects.get()
        original_profile = original.profile_id
        second_profile = two.get("/api/profile").json()["profile"]["id"]
        response = write(two, "register", {**SIGNUP, "password": "attacker-password"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "registration_failed")
        original.refresh_from_db()
        self.assertTrue(check_password(SIGNUP["password"], original.password))
        self.assertEqual(original.profile_id, original_profile)
        self.assertNotEqual(original.profile_id, second_profile)
        self.assertFalse(two.get("/api/guest-auth/session").json()["authenticated"])
        self.assertEqual(GuestAccount.objects.count(), 1)
        self.assertEqual(GuestProfile.objects.count(), 2)

    def test_sms_reset_cannot_be_skipped_with_phone_or_public_code(self):
        self.assertEqual(write(client(), "register", SIGNUP).status_code, 201)
        for data in [
            {"phone": PHONE, "password": "attacker-password"},
            {"challengeId": "any", "code": "000000", "password": "attacker-password"},
        ]:
            response = write(client(), "reset", data)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["code"], "sms_unavailable")
        response = write(client(), "challenges", {"phone": PHONE, "purpose": "reset"})
        self.assertEqual(response.status_code, 503)
        self.assertTrue(check_password(SIGNUP["password"], GuestAccount.objects.get().password))
        self.assertEqual(GuestChallenge.objects.count(), 0)

    def test_csrf_fields_password_and_phone_validation_still_apply(self):
        api = client()
        self.assertEqual(
            api.post("/api/guest-auth/register", SIGNUP, format="json").status_code, 403
        )
        for data, code in [
            ({**SIGNUP, "phone": "not-a-phone"}, "phone_invalid"),
            ({**SIGNUP, "password": "1234567"}, "weak_password"),
            ({**SIGNUP, "name": " "}, "name_invalid"),
            ({**SIGNUP, "phoneVerified": True}, "invalid_request"),
            ({**SIGNUP, "role": "admin"}, "invalid_request"),
        ]:
            response = write(api, "register", data)
            self.assertEqual(response.status_code, 422, response.content)
            self.assertEqual(response.json()["code"], code)
        self.assertEqual(GuestAccount.objects.count(), 0)

    def test_rate_limit_persists_outside_registration_transaction(self):
        self.assertEqual(write(client(), "register", SIGNUP).status_code, 201)
        for _ in range(4):
            self.assertEqual(write(client(), "register", SIGNUP).status_code, 409)
        response = write(client(), "register", SIGNUP)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "rate_limited")
        self.assertEqual(
            LoginAttempt.objects.get(pk=digest("guest-register:phone:" + PHONE)).count, 5
        )


@override_settings(**TEMPORARY)
class TemporaryRegistrationConcurrencyTests(TransactionTestCase):
    def test_concurrent_phone_registration_creates_one_identity(self):
        barrier = Barrier(2)

        def signup():
            close_old_connections()
            try:
                api = APIClient(enforce_csrf_checks=True)
                token = api.get("/api/auth/csrf").json()["token"]
                barrier.wait(timeout=10)
                return api.post(
                    "/api/guest-auth/register", SIGNUP, format="json", HTTP_X_CSRFTOKEN=token
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = sorted(pool.map(lambda _: signup(), range(2)))
        self.assertEqual(results, [201, 409])
        self.assertEqual(GuestAccount.objects.count(), 1)
        self.assertEqual(GuestChallenge.objects.count(), 0)
