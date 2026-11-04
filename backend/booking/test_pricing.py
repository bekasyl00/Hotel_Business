import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from .models import Audit, Booking, RoomPricePeriod
from .serializers import RoomSerializer
from .tests import fixture


class PricingTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.manager)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        self.start = timezone.localdate() + timedelta(days=30)

    def write(self, method, path, data):
        return getattr(self.client, method)(path, data, format="json", HTTP_X_CSRFTOKEN=self.token)

    def periods(self, price=20001):
        return [
            {
                "label": "Season",
                "start": str(self.start + timedelta(days=1)),
                "end": str(self.start + timedelta(days=3)),
                "price": price,
            }
        ]

    def save_periods(self, periods, version=1):
        return self.write(
            "patch", f"/api/rooms/{self.room.pk}", {"version": version, "pricePeriods": periods}
        )

    def book(self, children=None):
        self.client.logout()
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        data = {
            "roomId": self.room.pk,
            "tariffId": self.tariff.pk,
            "start": str(self.start),
            "end": str(self.start + timedelta(days=4)),
            "guests": 2,
            "guestLabel": "Fictional guest",
            "guestPhone": "+70000000000",
            "requestId": str(uuid.uuid4()),
        }
        if children is not None:
            data["childrenAges"] = children
        return self.write("post", "/api/my-bookings", data)

    def test_period_boundaries_child_policy_snapshot_and_receipt(self):
        self.room.price = 10001
        self.room.save()
        self.tariff.supplement = 101
        self.tariff.price_kind = "discount"
        self.tariff.discount_percent = 10
        self.tariff.children_under_three_free = True
        self.tariff.save()
        self.assertEqual(self.save_periods(self.periods()).status_code, 200)
        response = self.book([2])
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["total"], 54368)
        self.assertIsNone(data["nightly"])
        self.assertEqual(
            [line["nightly"] for line in data["nightlyBreakdown"]], [9092, 18092, 18092, 9092]
        )
        self.assertEqual(data["freeChildren"], 1)
        self.assertEqual(data["chargeableGuests"], 1)
        booking = Booking.objects.get(pk=data["id"])
        frozen = booking.snapshot.copy()
        RoomPricePeriod.objects.filter(room=self.room).update(price=999999)
        self.tariff.children_under_three_free = False
        self.tariff.save()
        booking.refresh_from_db()
        self.assertEqual(booking.snapshot, frozen)
        from commerce.models import DemoPayment
        from commerce.receipts import freeze_receipt

        payment = DemoPayment.objects.create(
            booking=booking,
            amount=data["total"],
            status="paid",
            outcome="success",
            request_key=uuid.uuid4(),
        )
        receipt = freeze_receipt(payment)
        self.assertEqual(receipt["nightlyBreakdown"], frozen["nightlyBreakdown"])
        self.assertEqual(receipt["total"], 54368)

    def test_overlap_rejected_and_updates_atomic_with_versions(self):
        p = self.periods()
        self.assertEqual(self.save_periods(p).status_code, 200)
        self.assertEqual(self.save_periods([], version=1).status_code, 409)
        before = Audit.objects.count()
        self.assertEqual(self.save_periods(p + p, version=2).status_code, 422)
        self.assertEqual(Audit.objects.count(), before)
        self.assertEqual(self.room.price_periods.count(), 1)
        self.assertEqual(self.save_periods([], version=2).status_code, 200)
        self.assertEqual(self.room.price_periods.count(), 0)

    def test_database_refuses_overlap_allows_adjacency(self):
        period = RoomPricePeriod.objects.create(
            room=self.room,
            label="a",
            price=100,
            stay=Range(self.start, self.start + timedelta(days=2), bounds="[)"),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoomPricePeriod.objects.create(room=self.room, label="b", price=200, stay=period.stay)
        RoomPricePeriod.objects.create(
            room=self.room,
            label="c",
            price=200,
            stay=Range(self.start + timedelta(days=2), self.start + timedelta(days=3), bounds="[)"),
        )

    def test_manager_cannot_change_other_resort_periods(self):
        from .models import Resort, Room

        other = Resort.objects.create(name="Other", city="City", address="Test", lat=0, lng=0)
        room = Room.objects.create(
            resort=other,
            number="1",
            title="Other",
            category="standard",
            area=20,
            capacity=2,
            beds="2",
            price=100,
        )
        response = self.write(
            "patch", f"/api/rooms/{room.pk}", {"version": 1, "pricePeriods": self.periods()}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(room.price_periods.exists())

    def test_age_three_is_paid_and_missing_ages_preserves_old_clients(self):
        self.tariff.children_under_three_free = True
        self.tariff.save()
        response = self.book([3])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["freeChildren"], 0)
        self.assertEqual(response.json()["total"], 108000)
        Booking.objects.all().delete()
        response = self.book()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["total"], 108000)

    def test_invalid_children_cannot_reduce_charges(self):
        for ages in [[-1], [18], [0, 0], ["bad"]]:
            self.assertEqual(self.book(ages).status_code, 422)
        self.assertFalse(Booking.objects.exists())

    def test_invalid_periods_and_partial_patch_preserves_calendar(self):
        for periods in [
            None,
            "bad",
            [{"label": "x", "start": "2027-02-30", "end": "2027-03-01", "price": 2}],
            [{"label": "x", "start": "2027-02-01", "end": "2027-02-01", "price": 2}],
        ]:
            self.assertEqual(self.save_periods(periods).status_code, 422)
        self.assertEqual(self.save_periods(self.periods()).status_code, 200)
        result = self.write("patch", f"/api/rooms/{self.room.pk}", {"version": 2, "price": 22000})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(RoomSerializer(self.room).data["pricePeriods"], self.periods())
