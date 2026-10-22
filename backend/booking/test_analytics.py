import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from commerce.models import DemoPayment, DemoRefund

from .models import Booking, Resort, Review, Room, Tariff
from .tests import fixture


def stamp(record, value):
    type(record).objects.filter(pk=record.pk).update(created_at=datetime.fromisoformat(value))
    return record


class AnalyticsTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.client = APIClient()
        self.client.force_login(self.manager)
        self.counter = 0

    def booking(
        self, amount=20000, status="confirmed", created="2026-10-10T12:00:00+05:00", other=False
    ):
        self.counter += 1
        start = timezone.localdate() + timedelta(days=self.counter * 3 + 10)
        resort, room, tariff = (
            (self.other, self.other_room, self.other_tariff)
            if other
            else (self.resort, self.room, self.tariff)
        )
        return stamp(
            Booking.objects.create(
                resort=resort,
                room=room,
                tariff=tariff,
                stay=Range(start, start + timedelta(days=1)),
                guests=1,
                guest_label="Private guest name",
                guest_phone="+70000000000",
                owner="private-owner",
                status=status,
                source="website",
                request_key=uuid.uuid4(),
                request_hash="test",
                snapshot={"total": amount},
            ),
            created,
        )

    def payment(self, booking, amount, created, status="paid", outcome="success"):
        return stamp(
            DemoPayment.objects.create(
                booking=booking,
                request_key=uuid.uuid4(),
                amount=amount,
                outcome=outcome,
                status=status,
            ),
            created,
        )

    def refund(self, payment, amount, created):
        return stamp(
            DemoRefund.objects.create(
                payment=payment, amount=amount, percent=70, actor_kind="guest"
            ),
            created,
        )

    def query(self, **params):
        return self.client.get(
            "/api/analytics", {"start": "2026-10-10", "end": "2026-10-11", **params}
        )

    def other_inventory(self):
        self.other = Resort.objects.create(
            name="Foreign resort", city="City", address="Secret address", lat=1, lng=1
        )
        self.other_room = Room.objects.create(
            resort=self.other,
            number="999",
            category="standard",
            title="Foreign room",
            capacity=1,
            area=20,
            beds="1",
            price=99999,
        )
        self.other_tariff = Tariff.objects.create(resort=self.other, name="Foreign tariff")

    def test_financial_events_use_their_own_dates_and_successful_original_amount(self):
        self.booking(status="pending")
        self.booking(amount=10000, status="cancelled", created="2026-10-08T12:00:00+05:00")
        old_booking = self.booking(amount=100000, created="2026-09-01T12:00:00+05:00")
        paid = self.payment(
            old_booking, 100000, "2026-10-10T12:00:00+05:00", status="partially_refunded"
        )
        self.refund(paid, 30000, "2026-10-11T12:00:00+05:00")
        older_booking = self.booking(created="2026-09-01T12:00:00+05:00")
        older_payment = self.payment(
            older_booking, 50000, "2026-10-01T12:00:00+05:00", status="refunded"
        )
        self.refund(older_payment, 50000, "2026-10-10T12:00:00+05:00")
        self.payment(
            older_booking, 99999, "2026-10-10T12:00:00+05:00", status="failed", outcome="failed"
        )
        stamp(
            Review.objects.create(
                resort=self.resort,
                booking=old_booking,
                text="Private review text",
                rating=4,
                status="approved",
            ),
            "2026-10-10T12:00:00+05:00",
        )
        stamp(
            Review.objects.create(
                resort=self.resort, booking=older_booking, text="Pending review", rating=1
            ),
            "2026-10-11T12:00:00+05:00",
        )
        response = self.query()
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(result["paymentMode"], "demo")
        totals = result["totals"]
        self.assertEqual(totals["bookingCount"], 1)
        self.assertEqual(totals["bookedAmount"], 20000)
        self.assertEqual(totals["grossReceived"], 100000)
        self.assertEqual(totals["refunds"], 80000)
        self.assertEqual(totals["netReceived"], 20000)
        self.assertEqual(totals["reviewCount"], 2)
        self.assertEqual(totals["averageRating"], 4)
        self.assertEqual(totals["statuses"]["pending"], 1)
        self.assertEqual(result["previousPeriod"], {"start": "2026-10-08", "end": "2026-10-09"})
        self.assertEqual(result["previousTotals"]["bookedAmount"], 10000)
        self.assertEqual(result["previousTotals"]["statuses"]["cancelled"], 1)
        self.assertEqual(result["series"][1]["netReceived"], -30000)
        self.assertEqual(result["byResort"][0]["netReceived"], 20000)
        self.assertEqual(result["byRoom"][0]["reviewCount"], 2)
        for private in [
            "Private guest name",
            "private-owner",
            "+70000000000",
            "Private review text",
            old_booking.id,
        ]:
            self.assertNotIn(private, response.content.decode())

    def test_tenant_isolation_options_and_explicit_filter(self):
        self.other_inventory()
        self.booking(amount=11111)
        foreign = self.booking(amount=99999, other=True)
        self.payment(foreign, 99999, "2026-10-10T12:00:00+05:00")
        response = self.query()
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(result["totals"]["bookedAmount"], 11111)
        self.assertEqual(result["totals"]["grossReceived"], 0)
        self.assertEqual(result["resorts"], [{"id": self.resort.id, "name": self.resort.name}])
        self.assertNotIn("Foreign", response.content.decode())
        self.assertEqual(self.query(resortId=self.other.id).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.query().json()["totals"]["bookingCount"], 2)
        self.assertEqual(self.query(resortId=self.other.id).json()["totals"]["bookedAmount"], 99999)
        self.assertEqual(self.query(resortId="missing").status_code, 404)
        self.client.logout()
        self.assertEqual(self.query().status_code, 401)

    def test_inclusive_almaty_dates_and_zero_filled_days(self):
        self.booking(amount=1, created="2026-10-09T18:59:59+00:00")
        self.booking(amount=2, created="2026-10-09T19:00:00+00:00")
        self.booking(amount=4, created="2026-10-12T18:59:59+00:00")
        self.booking(amount=8, created="2026-10-12T19:00:00+00:00")
        response = self.query(end="2026-10-12")
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(result["totals"]["bookedAmount"], 6)
        self.assertEqual([row["bookedAmount"] for row in result["series"]], [2, 0, 4])
        self.assertEqual(result["series"][1]["averageRating"], None)

    def test_week_month_buckets_and_same_period_totals(self):
        self.booking(created="2026-09-30T22:00:00+05:00")
        self.booking(created="2026-10-04T12:00:00+05:00")
        self.booking(created="2026-10-05T00:00:00+05:00")
        daily = self.query(start="2026-09-30", end="2026-10-06").json()
        weekly = self.query(start="2026-09-30", end="2026-10-06", granularity="week").json()
        monthly = self.query(start="2026-09-30", end="2026-10-06", granularity="month").json()
        self.assertEqual(weekly["totals"], daily["totals"])
        self.assertEqual([r["date"] for r in weekly["series"]], ["2026-09-28", "2026-10-05"])
        self.assertEqual([r["bookingCount"] for r in weekly["series"]], [2, 1])
        self.assertEqual([r["date"] for r in monthly["series"]], ["2026-09-01", "2026-10-01"])
        self.assertEqual([r["bookingCount"] for r in monthly["series"]], [1, 2])

    def test_empty_defaults_and_invalid_ranges(self):
        result = self.client.get("/api/analytics").json()
        self.assertEqual(len(result["series"]), 28)
        self.assertEqual(result["totals"]["netReceived"], 0)
        self.assertIsNone(result["totals"]["averageRating"])
        self.assertEqual(len(result["byRoom"]), 1)
        for params in [
            {"start": "bad"},
            {"start": "2026-10-12"},
            {"start": "2025-01-01"},
            {"granularity": "year"},
            {"start": "0001-01-01", "end": "0001-01-02"},
            {"start": "9999-12-30", "end": "9999-12-31"},
        ]:
            self.assertEqual(self.query(**params).status_code, 422)

    def test_breakdown_cap_does_not_truncate_totals(self):
        self.other_inventory()
        self.client.force_login(self.admin)
        own = self.booking(amount=100)
        foreign = self.booking(amount=200, other=True)
        self.payment(own, 100, "2026-10-10T12:00:00+05:00")
        self.payment(foreign, 200, "2026-10-10T12:00:00+05:00")
        with patch("booking.analytics.LIMIT", 1):
            result = self.query().json()
        self.assertEqual(result["totals"]["grossReceived"], 300)
        self.assertEqual(result["byResort"][0]["resortId"], self.other.id)
        self.assertEqual(result["byRoom"][0]["roomId"], self.other_room.id)
        self.assertEqual(result["truncated"], {"byResort": True, "byRoom": True})
