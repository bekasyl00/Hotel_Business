from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from psycopg.types.range import Range
from rest_framework.test import APIClient

from . import test_availability as calendar_tests
from .class_pricing import apply_period
from .errors import Problem
from .models import Audit, RoomPricePeriod, User
from .tests import authenticate_guest, fixture


class ClassPricingTests(TestCase):
    new_room = calendar_tests.AvailabilityCalendarTests.new_room
    reserve = calendar_tests.AvailabilityCalendarTests.reserve

    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.second = self.new_room("202", status="maintenance")
        self.other = self.new_room("301", category="comfort")
        self.client = APIClient(enforce_csrf_checks=True)
        self.url = f"/api/v1/resorts/{self.resort.pk}/class-pricing"
        self.login(self.manager)

    def login(self, user):
        self.client.force_login(user)
        self.csrf = self.client.get("/api/auth/csrf").json()["token"]

    def preview(self):
        response = self.client.get(self.url, {"category": "standard"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("no-store", response["Cache-Control"])
        return response.json()

    def payload(self):
        preview = self.preview()
        return {
            "category": preview["category"],
            "resortVersion": preview["resortVersion"],
            "rooms": [{"id": r["id"], "version": r["version"]} for r in preview["rooms"]],
            "period": {
                "label": "January",
                "start": "2027-01-12",
                "end": "2027-01-14",
                "price": 5000,
            },
        }

    def post(self, data=None):
        return self.client.post(
            self.url, data or self.payload(), format="json", HTTP_X_CSRFTOKEN=self.csrf
        )

    def period(self, room, start, end, price=8000):
        return RoomPricePeriod.objects.create(
            room=room, label="Individual", price=price, stay=Range(start, end, "[)")
        )

    def assert_untouched(self):
        self.assertEqual(RoomPricePeriod.objects.count(), 0)
        self.assertEqual(Audit.objects.count(), 0)
        for room in (self.room, self.second):
            room.refresh_from_db()
            self.assertEqual(room.version, 1)

    def test_applies_all_existing_class_rooms_once_and_calendar_reads_new_price(self):
        frozen = {"total": 12345, "nightlyBreakdown": [{"date": "2027-01-12", "nightly": 12345}]}
        booking = self.reserve(self.other)
        booking.snapshot = frozen
        booking.save(update_fields=["snapshot"])
        payload = self.payload()
        self.assertEqual({r["id"] for r in payload["rooms"]}, {self.room.pk, self.second.pk})
        response = self.post(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["appliedCount"], 2)
        self.assertEqual(RoomPricePeriod.objects.count(), 2)
        self.assertEqual(self.other.price_periods.count(), 0)
        for room in (self.room, self.second):
            room.refresh_from_db()
            self.assertEqual(room.version, 2)
        audit = Audit.objects.get()
        self.assertEqual((audit.entity, audit.action), ("roomPricePeriods", "apply_to_class"))
        self.assertEqual(audit.after["period"]["price"], 5000)
        with patch("booking.availability.timezone.now", return_value=calendar_tests.NOW):
            calendar = APIClient().get(
                "/api/v1/availability-calendar",
                {
                    "resortId": self.resort.pk,
                    "category": "standard",
                    "month": "2027-01",
                    "guests": 2,
                },
            )
        self.assertEqual(calendar.status_code, 200, calendar.content)
        self.assertEqual(calendar.json()["days"][11]["price"], 5500)
        self.assertEqual(calendar.json()["days"][13]["price"], 19800)
        booking.refresh_from_db()
        self.assertEqual(booking.snapshot, frozen)
        self.assertEqual(self.post(payload).status_code, 409)
        self.assertEqual(RoomPricePeriod.objects.count(), 2)
        self.assertEqual(Audit.objects.count(), 1)
        future_room = self.new_room("203")
        self.assertEqual(future_room.price_periods.count(), 0)

    def test_overlap_in_one_room_rolls_back_entire_class_and_keeps_individual_period(self):
        existing = self.period(self.second, date(2027, 1, 13), date(2027, 1, 15))
        response = self.post()
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "class_pricing_conflict")
        self.assertEqual(list(RoomPricePeriod.objects.values_list("pk", flat=True)), [existing.pk])
        self.assertEqual(self.room.price_periods.count(), 0)
        self.assertEqual(Audit.objects.count(), 0)
        self.second.refresh_from_db()
        self.assertEqual(self.second.version, 1)

    def test_adjacent_period_is_allowed_and_per_room_removal_still_works(self):
        self.period(self.second, date(2027, 1, 10), date(2027, 1, 12))
        self.assertEqual(self.post().status_code, 200)
        response = self.client.patch(
            f"/api/rooms/{self.room.pk}",
            {"version": 2, "pricePeriods": []},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.room.price_periods.count(), 0)
        self.assertEqual(self.second.price_periods.count(), 2)

    def test_one_room_limit_prevents_writes_everywhere(self):
        start = date(2025, 1, 1)
        for index in range(60):
            day = start + timedelta(days=index)
            self.period(self.second, day, day + timedelta(days=1))
        response = self.post()
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(RoomPricePeriod.objects.count(), 60)
        self.assertEqual(self.room.price_periods.count(), 0)
        self.assertEqual(Audit.objects.count(), 0)

    def test_stale_resort_room_versions_or_membership_cannot_partially_apply(self):
        original = self.payload()
        for change in ("resort", "room", "missing", "foreign"):
            data = deepcopy(original)
            if change == "resort":
                data["resortVersion"] += 1
            elif change == "room":
                data["rooms"][0]["version"] += 1
            elif change == "missing":
                data["rooms"].pop()
            else:
                data["rooms"].append({"id": self.other.pk, "version": 1})
            with self.subTest(change=change):
                self.assertEqual(self.post(data).status_code, 409)
                self.assert_untouched()
        self.new_room("203")
        self.assertEqual(self.post(original).status_code, 409)
        self.assert_untouched()

    def test_strict_validation_and_csrf(self):
        original = self.payload()
        invalid = []
        data = deepcopy(original)
        data["period"]["secret"] = "ignored?"
        invalid.append(data)
        data = deepcopy(original)
        data["unknown"] = True
        invalid.append(data)
        data = deepcopy(original)
        data["rooms"][0]["unknown"] = 1
        invalid.append(data)
        data = deepcopy(original)
        data["rooms"].append(data["rooms"][0])
        invalid.append(data)
        for period in (
            {"start": "2027-02-31"},
            {"end": "2027-01-12"},
            {"price": -1},
            {"price": 1.5},
            {"price": 10000001},
            {"label": " "},
        ):
            data = deepcopy(original)
            data["period"].update(period)
            invalid.append(data)
        for data in invalid:
            with self.subTest(data=data):
                self.assertIn(self.post(data).status_code, (400, 422))
                self.assert_untouched()
        response = self.client.post(self.url, original, format="json")
        self.assertEqual(response.status_code, 403)
        self.assert_untouched()

    def test_roles_ownership_and_archived_resort(self):
        data = self.payload()
        foreign_manager = User.objects.create_user(
            username="foreign", email="foreign@example.test", role="manager"
        )
        accountant = User.objects.create_user(
            username="accountant", email="accountant@example.test", role="accountant"
        )
        for user in (foreign_manager, accountant):
            self.login(user)
            self.assertEqual(self.client.get(self.url, {"category": "standard"}).status_code, 403)
            self.assertEqual(self.post(data).status_code, 403)
        self.client.logout()
        authenticate_guest(self.client)
        self.csrf = self.client.get("/api/auth/csrf").json()["token"]
        self.assertEqual(self.post(data).status_code, 401)
        self.assert_untouched()
        self.login(self.admin)
        self.resort.status = "archived"
        self.resort.save()
        self.assertEqual(self.post(data).status_code, 409)
        self.assert_untouched()
        self.resort.status = "draft"
        self.resort.save()
        self.assertEqual(self.post(data).status_code, 200)

    def test_empty_class_and_preview_input(self):
        empty = self.client.get(self.url, {"category": "suite"})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["roomCount"], 0)
        for query in ({}, {"category": "invalid"}, {"category": "standard", "resortId": "other"}):
            self.assertIn(self.client.get(self.url, query).status_code, (400, 422))
        self.assert_untouched()


class ConcurrentClassPricingTests(TransactionTestCase):
    def test_two_simultaneous_submissions_commit_only_one_group(self):
        resort, room, _, manager, _ = fixture()
        payload = {
            "category": "standard",
            "resortVersion": resort.version,
            "rooms": [{"id": room.pk, "version": room.version}],
            "period": {
                "label": "Simultaneous",
                "start": "2027-02-01",
                "end": "2027-02-03",
                "price": 5000,
            },
        }
        barrier = Barrier(2)

        def submit():
            close_old_connections()
            try:
                user = User.objects.get(pk=manager.pk)
                barrier.wait(timeout=10)
                try:
                    apply_period(SimpleNamespace(user=user, data=deepcopy(payload)), resort.pk)
                    return 200
                except Problem as exc:
                    return exc.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(RoomPricePeriod.objects.count(), 1)
        self.assertEqual(Audit.objects.count(), 1)
        room.refresh_from_db()
        self.assertEqual(room.version, 2)
