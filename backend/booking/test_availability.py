import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from psycopg.types.range import Range

from .models import Booking, Room
from .test_helpers import assert_calendar_query_budget
from .tests import fixture

NOW = datetime(2027, 1, 10, 0, tzinfo=UTC)


class AvailabilityCalendarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.resort, cls.room, cls.tariff, _, _ = fixture()

    def new_room(self, number, category="standard", capacity=2, status="active"):
        return Room.objects.create(
            resort=self.resort,
            number=number,
            category=category,
            title="Test room",
            area=20,
            capacity=capacity,
            beds="2",
            price=18000,
            status=status,
        )

    def reserve(self, room, start=12, end=14, status="confirmed", **extra):
        return Booking.objects.create(
            resort=self.resort,
            room=room,
            tariff=self.tariff,
            stay=Range(date(2027, 1, start), date(2027, 1, end), "[)"),
            status=status,
            guests=1,
            guest_label="Private guest",
            guest_phone="private",
            owner="private-owner",
            request_key=uuid.uuid4(),
            snapshot={},
            **extra,
        )

    def get(self, **extra):
        with patch("booking.availability.timezone.now", return_value=NOW):
            return self.client.get(
                "/api/v1/availability-calendar",
                {
                    "resortId": self.resort.pk,
                    "category": "standard",
                    "month": "2027-01",
                    "guests": 2,
                    **extra,
                },
            )

    def day(self, result, day):
        return result.json()["days"][day - 1]

    def test_scope_capacity_and_privacy(self):
        self.reserve(self.room)
        self.new_room("202", "comfort")
        self.new_room("203", capacity=1)
        self.new_room("204", status="maintenance")
        # Four bounded reads: resort, eligible rooms, monthly prices, booking ranges.
        with assert_calendar_query_budget(self):
            response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["totalRooms"], 1)
        self.assertEqual(self.day(response, 12)["availableRooms"], 0)
        with assert_calendar_query_budget(self, cold_quota=False):
            repeated = self.get()
        self.assertEqual(repeated.json(), response.json())
        self.assertEqual(self.day(self.get(category="comfort"), 12)["availableRooms"], 1)
        self.assertNotIn("private", response.content.decode().lower())
        self.assertEqual(
            set(self.day(response, 12)),
            {
                "date",
                "availableRooms",
                "departureRooms",
                "bookable",
                "price",
                "regularPrice",
                "priceKind",
                "hasPricePeriod",
                "periodLabel",
            },
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_holds_expiry_cancellation_and_checkout_exclusive(self):
        self.reserve(self.room, 12, 14, "pending", hold_expires_at=NOW + timedelta(minutes=10))
        self.reserve(self.room, 14, 15, "pending", hold_expires_at=NOW - timedelta(seconds=1))
        self.reserve(self.room, 15, 16, "cancelled")
        self.reserve(self.room, 16, 17, "pending")  # Legacy holds still occupy.
        response = self.get()
        self.assertEqual(
            [self.day(response, day)["availableRooms"] for day in range(12, 17)], [0, 0, 1, 1, 0]
        )

    def test_continuous_room_required_for_departure(self):
        second = self.new_room("202")
        self.reserve(self.room, 12, 13)
        self.reserve(second, 11, 12)
        response = self.get(arrival="2027-01-11")
        self.assertEqual(self.day(response, 11)["availableRooms"], 1)
        self.assertEqual(self.day(response, 12)["availableRooms"], 1)
        self.assertEqual(self.day(response, 12)["departureRooms"], 1)
        self.assertEqual(self.day(response, 13)["departureRooms"], 0)

        exact = self.get(roomId=self.room.pk, arrival="2027-01-11")
        self.assertEqual(exact.json()["totalRooms"], 1)
        self.assertEqual(self.day(exact, 12)["availableRooms"], 0)
        self.assertEqual(self.day(exact, 12)["departureRooms"], 1)

    def test_exact_room_must_match_scope_and_unpublished_resort_is_hidden(self):
        other = self.new_room("202", "comfort")
        self.assertEqual(self.get(roomId=other.pk).status_code, 404)
        self.resort.status = "draft"
        self.resort.save()
        self.assertEqual(self.get().status_code, 404)

    def test_bounded_inputs_and_property_local_cutoff(self):
        for extra in [
            {"month": "2027-13"},
            {"month": "0000-01"},
            {"month": "2099-01"},
            {"month": "2026-12"},
            {"guests": 0},
            {"category": "all"},
            {"arrival": "2027-02-30"},
            {"arrival": "2026-01-01"},
        ]:
            self.assertIn(self.get(**extra).status_code, (400, 422))
        response = self.get(arrival="2027-01-10")
        self.assertFalse(self.day(response, 9)["bookable"])
        self.assertEqual(self.day(response, 10)["availableRooms"], 1)
        self.assertEqual(self.day(response, 11)["departureRooms"], 1)
        self.resort.check_in_time = "04:00"
        self.resort.save()
        response = self.get(arrival="2027-01-10")  # 05:00 in Asia/Almaty.
        self.assertFalse(self.day(response, 10)["bookable"])
        self.assertEqual(self.day(response, 11)["departureRooms"], 0)

    def test_cross_month_departures_cannot_skip_occupied_nights(self):
        self.reserve(self.room, 30, 31)
        response = self.get(month="2027-02", arrival="2027-01-29")
        self.assertEqual(len(response.json()["days"]), 28)
        self.assertEqual(self.day(response, 1)["availableRooms"], 1)
        self.assertEqual(self.day(response, 1)["departureRooms"], 0)
