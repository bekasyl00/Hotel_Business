import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from booking.errors import Problem
from booking.models import Audit, Booking, Resort, Review, Room, Tariff, User

from .models import DemoPayment, DemoRefund
from .services import (
    apply_cancellation,
    cancellation_preview,
    create_demo_payment,
    freeze_cancellation_terms,
)


def fixture():
    resort = Resort.objects.create(
        name="Демо-санаторий",
        city="Сарыагаш",
        address="Тест",
        lat=41,
        lng=69,
        status="published",
    )
    room = Room.objects.create(
        resort=resort,
        number="101",
        category="standard",
        title="Стандарт",
        area=20,
        capacity=2,
        beds="2",
        price=18000,
    )
    tariff = Tariff.objects.create(resort=resort, name="Проживание")
    manager = User.objects.create(
        username="payments@example.test",
        email="payments@example.test",
        name="Управляющий",
        resort=resort,
    )
    start = timezone.localdate() + timedelta(days=5)
    booking = Booking.objects.create(
        resort=resort,
        room=room,
        tariff=tariff,
        stay=Range(start, start + timedelta(days=2)),
        guests=2,
        guest_label="Демо-гость",
        owner="owner-a",
        source="website",
        status="confirmed",
        request_key=uuid.uuid4(),
        request_hash="test",
        snapshot={"total": 36000, "cancellationPolicy": freeze_cancellation_terms(resort, start)},
    )
    return resort, booking, manager


class CommerceTests(TestCase):
    def setUp(self):
        self.resort, self.booking, self.manager = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        session = self.client.session
        session["guest_owner"] = self.booking.owner
        session.save()
        self.payload = {
            "bookingId": self.booking.pk,
            "requestId": str(uuid.uuid4()),
            "outcome": "success",
        }

    def pay(self, **changes):
        return self.client.post(
            "/api/payments/demo",
            {**self.payload, **changes},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )

    def test_payment_snapshot_csrf_and_idempotency(self):
        self.assertEqual(
            self.client.post("/api/payments/demo", self.payload, format="json").status_code, 403
        )
        self.booking.room.price = 1
        self.booking.room.save()
        first = self.pay(amount=1)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["amount"], 36000)
        self.assertEqual(first.json()["paymentMode"], "demo")
        self.assertEqual(first.json()["status"], "paid")
        self.assertEqual(self.pay().json()["id"], first.json()["id"])
        self.assertEqual(self.pay(outcome="failed").status_code, 409)
        self.assertEqual(self.pay(requestId=str(uuid.uuid4())).status_code, 409)
        self.assertEqual(DemoPayment.objects.count(), 1)
        self.assertEqual(Audit.objects.filter(action="demo_payment").count(), 1)

    def test_failed_payment_can_retry_with_new_request(self):
        first = self.pay(outcome="failed")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "failed")
        self.assertEqual(cancellation_preview(self.booking)["paidAmount"], 0)
        self.assertEqual(self.pay(outcome="failed").json()["id"], first.json()["id"])
        self.assertEqual(self.pay(requestId=str(uuid.uuid4())).json()["status"], "paid")
        self.assertEqual(DemoPayment.objects.count(), 2)

    def test_payment_owner_and_status_restrictions(self):
        self.booking.owner = "someone-else"
        self.booking.save()
        self.assertEqual(self.pay().status_code, 404)
        self.booking.owner = "owner-a"
        for status in ["pending", "rejected", "cancelled"]:
            self.booking.status = status
            self.booking.save()
            self.assertEqual(self.pay().status_code, 409)
        self.booking.status, self.booking.source = "confirmed", "staff"
        self.booking.save()
        self.assertEqual(self.pay().status_code, 404)
        self.assertEqual(DemoPayment.objects.count(), 0)

    def test_payment_requires_future_checkin(self):
        checkin = datetime.fromisoformat(self.booking.snapshot["cancellationPolicy"]["checkinAt"])
        with patch("commerce.services.timezone.now", return_value=checkin):
            self.assertEqual(self.pay().status_code, 409)

    def test_refund_boundaries_and_timezone(self):
        self.pay()
        checkin = datetime.fromisoformat(self.booking.snapshot["cancellationPolicy"]["checkinAt"])
        for hours, seconds, percent in [(48, 0, 100), (48, 1, 70), (24, 0, 70), (24, 1, 0)]:
            now = checkin - timedelta(hours=hours) + timedelta(seconds=seconds)
            preview = cancellation_preview(self.booking, now=now.astimezone(ZoneInfo("UTC")))
            self.assertEqual(preview["refundPercent"], percent)
            self.assertEqual(preview["refundAmount"], 36000 * percent // 100)
        self.assertEqual(cancellation_preview(self.booking, now=checkin)["refundAmount"], 0)

    def test_checkin_policy_is_frozen(self):
        self.resort.check_in_time = time(18, 30)
        self.resort.time_zone = "Asia/Almaty"
        terms = freeze_cancellation_terms(self.resort, self.booking.stay.lower)
        self.assertTrue(terms["checkinAt"].endswith("18:30:00+05:00"))
        self.booking.snapshot["cancellationPolicy"] = terms
        self.resort.check_in_time = time(10)
        preview = cancellation_preview(self.booking)
        self.assertEqual(preview["checkInTime"], "18:30")
        self.assertEqual(preview["partialRefundPercent"], 70)

    def test_preview_scope(self):
        self.pay()
        url = "/api/cancellation-preview/" + self.booking.pk
        self.assertEqual(self.client.get(url).json()["paidAmount"], 36000)
        self.assertEqual(APIClient().get(url).status_code, 404)
        self.assertEqual(self.client.get(url + "?asStaff=true").status_code, 401)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(url + "?asStaff=true").json()["actorKind"], "provider")
        other = Resort.objects.create(name="Другой", city="Тест", address="Тест", lat=40, lng=70)
        self.manager.resort = other
        self.manager.save()
        self.assertEqual(self.client.get(url + "?asStaff=true").status_code, 403)

    def test_cancellation_is_atomic_and_idempotent(self):
        self.pay()
        checkin = datetime.fromisoformat(self.booking.snapshot["cancellationPolicy"]["checkinAt"])
        now = checkin - timedelta(hours=30)
        with patch("commerce.services.timezone.now", return_value=now):
            result = apply_cancellation(self.booking, AnonymousUser())
            again = apply_cancellation(self.booking, AnonymousUser())
        self.assertEqual(result, again)
        self.assertEqual(result["refundAmount"], 25200)
        payment = DemoPayment.objects.get()
        self.assertEqual(payment.status, "partially_refunded")
        self.assertEqual(payment.refunded_amount, 25200)
        self.assertEqual(DemoRefund.objects.count(), 1)
        self.assertEqual(Audit.objects.filter(action="demo_refund").count(), 1)
        later_preview = cancellation_preview(self.booking, now=checkin)
        self.assertEqual(later_preview["refundAmount"], 25200)
        self.assertTrue(later_preview["finalized"])

    def test_late_cancellation_zero_for_guest_and_staff(self):
        self.pay()
        checkin = datetime.fromisoformat(self.booking.snapshot["cancellationPolicy"]["checkinAt"])
        with patch("commerce.services.timezone.now", return_value=checkin - timedelta(hours=12)):
            self.assertEqual(cancellation_preview(self.booking)["refundAmount"], 0)
            result = apply_cancellation(self.booking, self.manager, staff=True)
        self.assertEqual(result["refundAmount"], 0)
        self.assertEqual(DemoPayment.objects.get().status, "paid")
        self.assertEqual(DemoRefund.objects.get().percent, 0)

    def test_failed_audit_rolls_back_payment(self):
        request = SimpleNamespace(
            user=AnonymousUser(), session={"guest_owner": "owner-a"}, data=self.payload
        )
        with patch("booking.services.log_change", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                create_demo_payment(request)
        self.assertEqual(DemoPayment.objects.count(), 0)

    def test_outer_cancellation_transaction_rolls_back_refund(self):
        self.pay()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                apply_cancellation(self.booking, self.manager, staff=True)
                raise RuntimeError("booking update failed")
        self.assertEqual(DemoRefund.objects.count(), 0)
        self.assertEqual(DemoPayment.objects.get().status, "paid")

    def test_booking_api_freezes_discount_price_and_checkin(self):
        room, tariff = self.booking.room, self.booking.tariff
        room.price = 5
        room.save()
        tariff.price_kind, tariff.discount_percent = "discount", 50
        tariff.save()
        self.resort.check_in_time = time(17, 45)
        self.resort.save()
        start = self.booking.stay.upper + timedelta(days=2)
        payload = {
            "roomId": room.pk,
            "tariffId": tariff.pk,
            "start": str(start),
            "end": str(start + timedelta(days=3)),
            "guests": 2,
            "guestLabel": "Тестовый гость",
            "guestPhone": "+70000000000",
            "requestId": str(uuid.uuid4()),
            "total": 1,
            "discountPercent": 99,
        }
        result = self.client.post(
            "/api/my-bookings", payload, format="json", HTTP_X_CSRFTOKEN=self.token
        )
        self.assertEqual(result.status_code, 201, result.content)
        data = result.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["regularNightly"], 5)
        self.assertEqual(data["nightly"], 3)
        self.assertEqual(data["total"], 9)
        self.assertEqual(data["discountPercent"], 50)
        self.assertEqual(data["cancellationPolicy"]["checkInTime"], "17:45")
        self.assertTrue(data["cancellationPolicy"]["checkinAt"].endswith("17:45:00+05:00"))
        self.assertIsNone(data["payment"])
        self.assertIsNone(data["reviewId"])
        self.resort.check_in_time = time(10)
        self.resort.save()
        tariff.discount_percent = 10
        tariff.save()
        replay = self.client.post(
            "/api/my-bookings", payload, format="json", HTTP_X_CSRFTOKEN=self.token
        ).json()
        self.assertEqual(replay["id"], data["id"])
        self.assertEqual(replay["nightly"], 3)
        self.assertEqual(replay["cancellationPolicy"]["checkInTime"], "17:45")

    def test_booking_api_cancel_refunds_and_returns_snapshot(self):
        self.pay()
        checkin = datetime.fromisoformat(self.booking.snapshot["cancellationPolicy"]["checkinAt"])
        with patch("commerce.services.timezone.now", return_value=checkin - timedelta(hours=30)):
            result = self.client.patch(
                "/api/my-bookings/" + self.booking.pk,
                {"status": "cancelled", "version": 1},
                format="json",
                HTTP_X_CSRFTOKEN=self.token,
            )
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["status"], "cancelled")
        self.assertEqual(result.json()["cancellation"]["refundAmount"], 25200)
        self.assertEqual(result.json()["payment"]["status"], "partially_refunded")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.snapshot["cancellation"]["refundPercent"], 70)
        self.assertEqual(DemoRefund.objects.count(), 1)
        self.assertEqual(
            self.client.get("/api/my-bookings").json()[0]["payment"]["refundedAmount"], 25200
        )

    def test_booking_api_audit_failure_rolls_back_status_and_refund(self):
        from booking.services import log_change

        self.pay()

        def failing_booking_audit(user, entity, *args, **kwargs):
            if entity == "bookings":
                raise RuntimeError("booking audit unavailable")
            return log_change(user, entity, *args, **kwargs)

        with patch("booking.services.log_change", side_effect=failing_booking_audit):
            with self.assertRaises(RuntimeError):
                self.client.patch(
                    "/api/my-bookings/" + self.booking.pk,
                    {"status": "cancelled", "version": 1},
                    format="json",
                    HTTP_X_CSRFTOKEN=self.token,
                )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "confirmed")
        self.assertEqual(self.booking.version, 1)
        self.assertNotIn("cancellation", self.booking.snapshot)
        self.assertEqual(DemoPayment.objects.get().status, "paid")
        self.assertEqual(DemoRefund.objects.count(), 0)
        self.assertEqual(Audit.objects.filter(action="demo_refund").count(), 0)

    def test_booking_list_exposes_own_review_status(self):
        review = Review.objects.create(
            resort=self.resort,
            booking=self.booking,
            rating=4,
            text="Тестовый отзыв о проживании",
        )
        result = self.client.get("/api/my-bookings").json()[0]
        self.assertEqual(result["reviewId"], review.pk)
        self.assertEqual(result["reviewStatus"], "pending")
        review.status = "approved"
        review.save()
        result = self.client.get("/api/my-bookings").json()[0]
        self.assertEqual(result["reviewStatus"], "approved")


class ConcurrentPaymentTests(TransactionTestCase):
    def test_double_payment_from_concurrent_requests(self):
        _, booking, _ = fixture()
        barrier = Barrier(2)

        def pay():
            close_old_connections()
            try:
                request = SimpleNamespace(
                    user=AnonymousUser(),
                    session={"guest_owner": booking.owner},
                    data={
                        "bookingId": booking.pk,
                        "requestId": str(uuid.uuid4()),
                        "outcome": "success",
                    },
                )
                barrier.wait(timeout=10)
                try:
                    create_demo_payment(request)
                    return 200
                except Problem as exc:
                    return exc.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(pay), pool.submit(pay)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(DemoPayment.objects.filter(outcome="success").count(), 1)
