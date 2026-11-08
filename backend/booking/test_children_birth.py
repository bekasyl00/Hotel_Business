import json
import uuid
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Audit, Booking
from .serializers import BookingInput
from .tests import authenticate_guest, fixture


class ChildBirthTests(TestCase):
    def payload(self, **changes):
        return {
            "roomId": "room",
            "tariffId": "tariff",
            "start": "2027-11-08",
            "end": "2027-11-10",
            "guests": 2,
            "guestLabel": "Fictional parent",
            "guestPhone": "+70000000000",
            "requestId": str(uuid.uuid4()),
            "childrenBirthDates": ["2024-11-09"],
            **changes,
        }

    def test_age_on_arrival_and_discard_birthdate_after_validation(self):
        inp = BookingInput(data=self.payload())
        self.assertTrue(inp.is_valid(), inp.errors)
        self.assertEqual(inp.validated_data["childrenAges"], [2])
        self.assertNotIn("childrenBirthDates", inp.validated_data)
        inp = BookingInput(data=self.payload(start="2027-11-09"))
        self.assertTrue(inp.is_valid(), inp.errors)
        self.assertEqual(inp.validated_data["childrenAges"], [3])

    def test_invalid_dates_adult_or_spoofed_age_rejected(self):
        for changes in [
            {"childrenBirthDates": ["2023-02-29"]},
            {"childrenBirthDates": ["2000-01-01"]},
            {"childrenBirthDates": ["2099-01-01"]},
            {"childrenAges": [0]},
            {"iin": "000000000000"},
        ]:
            with self.subTest(changes=changes):
                self.assertFalse(BookingInput(data=self.payload(**changes)).is_valid())

    def test_child_boundary_is_fourteenth_birthday_on_checkin(self):
        inp = BookingInput(data=self.payload(childrenBirthDates=["2013-11-09"]))
        self.assertTrue(inp.is_valid(), inp.errors)
        self.assertEqual(inp.validated_data["childrenAges"], [13])
        inp = BookingInput(data=self.payload(start="2027-11-09", childrenBirthDates=["2013-11-09"]))
        self.assertFalse(inp.is_valid())
        self.assertFalse(
            BookingInput(data=self.payload(childrenBirthDates=[], childrenAges=[14])).is_valid()
        )

    def test_second_birthday_ends_opt_in_supplement_exemption(self):
        from .pricing import quote_stay

        _, room, tariff, _, _ = fixture()
        tariff.children_under_two_free = True
        tariff.supplement = 1000
        for checkin, age, free in [("2027-11-08", 1, 1), ("2027-11-09", 2, 0)]:
            inp = BookingInput(data=self.payload(start=checkin, childrenBirthDates=["2025-11-09"]))
            self.assertTrue(inp.is_valid(), inp.errors)
            data = inp.validated_data
            self.assertEqual(data["childrenAges"], [age])
            quote = quote_stay(
                room,
                tariff,
                data["start"],
                data["start"] + timedelta(days=1),
                2,
                data["childrenAges"],
            )
            self.assertEqual(quote["freeChildren"], free)
            self.assertEqual(quote["total"], room.price + 1000 * (2 - free))
            self.assertEqual(quote["pricingVersion"], 3)
            self.assertNotIn("childrenUnderThreeFree", quote)

    def test_booking_and_audit_only_keep_age(self):
        resort, room, tariff, _, _ = fixture()
        tariff.children_under_two_free = True
        tariff.supplement = 1000
        tariff.save()
        today = timezone.localdate()
        birth = (
            today.replace(year=today.year - 1)
            if (today.month, today.day) != (2, 29)
            else date(today.year - 1, 2, 28)
        )
        client = APIClient(enforce_csrf_checks=True)
        authenticate_guest(client)
        csrf = client.get("/api/auth/csrf").json()["token"]
        response = client.post(
            "/api/my-bookings",
            self.payload(
                roomId=room.pk,
                tariffId=tariff.pk,
                start=str(today + timedelta(days=7)),
                end=str(today + timedelta(days=9)),
                childrenBirthDates=[str(birth)],
            ),
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 201, response.content)
        b = Booking.objects.get(pk=response.json()["id"])
        self.assertEqual(b.snapshot["childrenAges"], [1])
        self.assertEqual(b.snapshot["freeChildren"], 1)
        stored = json.dumps(b.snapshot) + json.dumps(list(Audit.objects.values("before", "after")))
        self.assertNotIn(str(birth), stored)
        self.assertNotIn("childrenBirthDates", response.content.decode())
