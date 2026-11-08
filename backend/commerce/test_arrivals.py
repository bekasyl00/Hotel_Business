from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from psycopg.types.range import Range

from booking.errors import Problem
from booking.models import Audit, User

from . import test_bank_payments as bank
from .arrivals import booking_id_from_code, ticket_code
from .models import OnsiteSettlement
from .test_settlement import SettlementTests


@override_settings(**bank.BANK)
class ArrivalTests(TestCase):
    setUp = bank.BankTests.setUp
    create = bank.BankTests.create
    payment = bank.BankTests.payment
    terms = SettlementTests.terms
    paid = SettlementTests.paid
    login = SettlementTests.login
    post = SettlementTests.post

    def ready(self):
        self.paid()
        today = timezone.localdate()
        self.booking.stay = Range(today, today + timedelta(days=2), "[)")
        self.booking.save(update_fields=["stay"])
        self.login(self.manager)

    def accept(self, **overrides):
        return self.post(
            f"/api/bookings/{self.booking.pk}/accept-arrival",
            {
                "version": self.booking.version,
                "method": "cash",
                "received": True,
                **overrides,
            },
        )

    def resolve(self, code=None):
        return self.post("/api/staff/arrivals/resolve", {"code": code or ticket_code(self.booking)})

    def test_qr_signed_private_and_scope_enforced(self):
        self.paid()
        code = ticket_code(self.booking)
        self.assertEqual(booking_id_from_code(code), self.booking.pk)
        self.assertNotIn(self.booking.guest_label, code)
        self.assertEqual(self.resolve(code).status_code, 401)
        self.login(self.manager)
        response = self.resolve(code)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "outside_dates")
        self.assertEqual(self.resolve("TYNYS-" + self.booking.pk.upper()).status_code, 200)
        self.assertEqual(self.resolve(code + "x").status_code, 422)
        other = User.objects.create_user(
            username="other-arrival", email="other-arrival@test.invalid", role="manager"
        )
        self.login(other)
        self.assertEqual(self.resolve(code).status_code, 403)
        accountant = User.objects.create_user(
            username="accountant-arrival",
            email="accountant-arrival@test.invalid",
            role="accountant",
        )
        self.login(accountant)
        self.assertEqual(self.resolve(code).status_code, 403)
        self.assertEqual(self.accept().status_code, 403)

    def test_preview_never_mutates_and_accept_is_atomic_idempotent(self):
        self.ready()
        self.assertEqual(self.resolve().json()["state"], "ready")
        self.booking.refresh_from_db()
        self.assertIsNone(self.booking.checked_in_at)
        self.assertFalse(OnsiteSettlement.objects.exists())
        body = {"version": self.booking.version, "method": "cash", "received": True}
        path = f"/api/bookings/{self.booking.pk}/accept-arrival"
        response = self.post(path, body)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["stayStatus"], "in_house")
        self.assertEqual(response.json()["onsitePayment"]["amount"], 280000)
        self.assertEqual(self.post(path, body).status_code, 200)
        self.assertEqual(OnsiteSettlement.objects.count(), 1)
        self.assertEqual(Audit.objects.filter(action="check-in").count(), 1)
        self.assertEqual(self.resolve().json()["state"], "accepted")

    def test_received_version_csrf_dates_and_unknown_amount(self):
        self.ready()
        self.assertEqual(self.accept(received=False).status_code, 422)
        self.assertEqual(self.accept(version=1).status_code, 409)
        self.assertEqual(self.accept(amount=1).status_code, 422)
        self.assertEqual(
            self.client.post(
                f"/api/bookings/{self.booking.pk}/accept-arrival", {}, format="json"
            ).status_code,
            403,
        )
        self.booking.stay = Range(
            timezone.localdate() + timedelta(days=3), timezone.localdate() + timedelta(days=5), "[)"
        )
        self.booking.save(update_fields=["stay"])
        self.assertEqual(self.accept().status_code, 409)
        self.assertFalse(OnsiteSettlement.objects.exists())

    def test_failed_checkin_rolls_back_onsite_collection(self):
        self.ready()
        with patch("commerce.arrivals.change_stay", side_effect=Problem("conflict", 409)):
            self.assertEqual(self.accept().status_code, 409)
        self.assertFalse(OnsiteSettlement.objects.exists())
        self.assertFalse(Audit.objects.filter(action="onsite_payment_recorded").exists())

    def test_cancelled_and_departed_never_accept_old_qr(self):
        self.ready()
        code = ticket_code(self.booking)
        self.booking.status = "cancelled"
        self.booking.save(update_fields=["status"])
        self.assertIsNone(ticket_code(self.booking))
        self.assertEqual(self.resolve(code).status_code, 409)
        self.assertEqual(self.accept().status_code, 409)
        self.booking.status = "confirmed"
        self.booking.checked_in_at = self.booking.checked_out_at = timezone.now()
        self.booking.save(update_fields=["status", "checked_in_at", "checked_out_at"])
        self.assertIsNone(ticket_code(self.booking))
        self.assertEqual(self.resolve(code).json()["state"], "departed")
        self.assertEqual(self.accept().status_code, 409)

    def test_existing_collection_can_checkin_without_second_collection(self):
        self.ready()
        self.post(
            f"/api/bookings/{self.booking.pk}/onsite-payment",
            {"version": self.booking.version, "method": "card", "received": True},
        )
        self.booking.refresh_from_db()
        self.assertEqual(self.accept(received=False).status_code, 200)
        self.assertEqual(OnsiteSettlement.objects.count(), 1)
        self.assertEqual(OnsiteSettlement.objects.get().method, "card")

    def test_legacy_full_online_can_checkin_without_onsite_payment(self):
        from .payment_services import apply_transaction

        payment = self.payment()
        apply_transaction(payment.pk, bank.evidence(payment))
        self.booking.refresh_from_db()
        today = timezone.localdate()
        self.booking.stay = Range(today, today + timedelta(days=2), "[)")
        self.booking.save(update_fields=["stay"])
        self.login(self.manager)
        self.assertEqual(self.accept(received=False).status_code, 200)
        self.assertFalse(OnsiteSettlement.objects.exists())
