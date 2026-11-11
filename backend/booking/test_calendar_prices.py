from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from psycopg.types.range import Range

from . import test_availability as calendar_tests
from .models import RoomPricePeriod
from .test_helpers import assert_calendar_query_budget
from .tests import fixture


class CalendarPriceTests(TestCase):
    new_room = calendar_tests.AvailabilityCalendarTests.new_room
    reserve = calendar_tests.AvailabilityCalendarTests.reserve
    get = calendar_tests.AvailabilityCalendarTests.get
    day = calendar_tests.AvailabilityCalendarTests.day

    def setUp(self):
        self.resort, self.room, self.tariff, _, _ = fixture()
        self.resort.commission_percent = Decimal("10")
        self.resort.save()
        self.room.price = 10000
        self.room.save()

    def period(self, room=None, *, start=12, end=14, price=5000, label="Season"):
        return RoomPricePeriod.objects.create(
            room=room or self.room,
            label=label,
            stay=Range(date(2027, 1, start), date(2027, 1, end), "[)"),
            price=price,
        )

    def test_season_boundary_inclusive_markup_and_no_tariff_supplement(self):
        self.room.price = 10001
        self.room.save()
        self.resort.commission_percent = Decimal("7.25")
        self.resort.save()
        self.tariff.supplement = 99999
        self.tariff.save()
        self.period()
        result = self.get(roomId=self.room.pk)
        self.assertEqual(result.status_code, 200, result.content)
        before, first, final, after = [self.day(result, day) for day in (11, 12, 13, 14)]
        self.assertEqual(before["price"], 21452)
        self.assertEqual(first["price"], 10725)
        self.assertEqual(final["price"], 10725)
        self.assertEqual(after["price"], 21452)
        self.assertEqual(first["regularPrice"], 21452)
        self.assertEqual(first["priceKind"], "discount")
        self.assertTrue(first["hasPricePeriod"])
        self.assertEqual(first["periodLabel"], "Season")
        self.assertEqual(after["priceKind"], "regular")
        self.assertFalse(after["hasPricePeriod"])

    def test_class_price_excludes_occupied_rooms_and_wrong_capacity_status_or_class(self):
        self.period(start=11, end=15)
        self.reserve(self.room)
        second = self.new_room("available")
        second.price = 8000
        second.save()
        for room in (
            self.new_room("too-small", capacity=1),
            self.new_room("other-class", category="comfort"),
            self.new_room("maintenance", status="maintenance"),
        ):
            self.period(room, start=11, end=15, price=1)
        with assert_calendar_query_budget(self):
            result = self.get()
        self.assertEqual(self.day(result, 11)["price"], 11000)
        during = self.day(result, 12)
        self.assertEqual(during["price"], 17600)
        self.assertEqual(during["regularPrice"], 17600)
        self.assertEqual(during["priceKind"], "regular")
        self.assertFalse(during["hasPricePeriod"])
        self.assertEqual(self.day(result, 14)["price"], 11000)

    def test_period_increase_or_equal_price_is_seasonal_not_discount(self):
        self.period(price=12000)
        self.period(start=14, end=16, price=10000)
        result = self.get()
        high = self.day(result, 12)
        self.assertEqual((high["price"], high["regularPrice"]), (26400, 22000))
        self.assertEqual(high["priceKind"], "seasonal")
        same = self.day(result, 14)
        self.assertEqual((same["price"], same["regularPrice"]), (22000, 22000))
        self.assertEqual(same["priceKind"], "seasonal")
        self.assertTrue(same["hasPricePeriod"])

    def test_equal_current_prices_keep_regular_price_of_stable_selected_room(self):
        self.period()
        second = self.new_room("second")
        second.price = 20000
        second.save()
        self.period(second)
        day = self.day(self.get(), 12)
        selected = min((self.room, second), key=lambda room: room.pk)
        self.assertEqual(day["price"], 11000)
        self.assertEqual(day["regularPrice"], int(selected.price * Decimal("1.1")) * 2)

    def test_past_busy_departure_only_and_outside_horizon_have_no_nightly_price(self):
        self.period()
        self.reserve(self.room)
        result = self.get(roomId=self.room.pk, arrival="2027-01-11")
        departure = self.day(result, 12)
        self.assertEqual((departure["departureRooms"], departure["availableRooms"]), (1, 0))
        for day in (self.day(result, 9), departure, self.day(self.get(month="2028-01"), 11)):
            self.assertIsNone(day["price"])
            self.assertIsNone(day["regularPrice"])
            self.assertIsNone(day["priceKind"])
            self.assertFalse(day["hasPricePeriod"])

    def test_unconfigured_rate_retains_base_display_and_overlap_constraint(self):
        self.resort.commission_percent = None
        self.resort.save()
        self.period()
        self.assertEqual(self.day(self.get(), 12)["price"], 10000)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            self.period(start=13, end=15, price=1234)
        self.resort.commission_percent = Decimal(0)
        self.resort.save()
        self.assertEqual(self.day(self.get(), 12)["price"], 10000)
