import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from booking.models import (
    Booking,
    BookingAllocation,
    Resort,
    Room,
    RoomPlace,
    StaffNotification,
    StaffPushDelivery,
    StaffPushDevice,
    User,
)
from booking.test_helpers import unrelated_owner
from commerce.vouchers import voucher_data

from .tests import authenticate_guest, fixture


class BedInventoryAndNotificationsTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        # Configure a 3-place room (102a, 102b, 102c) with 20,000 KZT/night base price
        self.room3 = Room.objects.create(
            id=f"{self.resort.pk}-102",
            resort=self.resort,
            number="102",
            category="standard",
            title="Трёхместный стандарт",
            area=28,
            capacity=3,
            beds="Три односпальные кровати",
            price=20000,
            status="active",
        )
        self.tariff.supplement = 0
        self.tariff.children_under_two_free = True
        self.tariff.save()
        self.start = timezone.localdate() + timedelta(days=7)
        self.end = self.start + timedelta(days=7)

    def _guest_client(self, idx=1):
        client = APIClient(enforce_csrf_checks=True)
        authenticate_guest(client, phone=f"+7701000010{idx}", name=f"Guest {idx}")
        token = client.get("/api/auth/csrf").json()["token"]
        return client, token

    def _staff_client(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        token = client.get("/api/auth/csrf").json()["token"]
        return client, token

    def test_partial_room_occupancy_and_overcapacity_rejection(self):
        places = list(self.room3.places.filter(status="active").order_by("position"))
        self.assertEqual([p.unit_label for p in places], ["102a", "102b", "102c"])

        # Buyer 1 books 1 of 3 places -> 102a occupied, 102b and 102c remain available
        c1, t1 = self._guest_client(1)
        r1 = c1.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 1,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t1,
        )
        self.assertEqual(r1.status_code, 201, r1.content)
        b1 = r1.json()
        self.assertEqual(b1["placeLabels"], ["102a"])
        self.assertEqual(b1["placesCount"], 1)

        # Availability shows room3 is still available for 2 guests (2 places left)
        avail_2 = c1.get(
            "/api/availability",
            {"start": str(self.start), "end": str(self.end), "guests": 2},
        )
        self.assertEqual(avail_2.status_code, 200)
        self.assertIn(self.room3.pk, avail_2.json()["roomIds"])
        self.assertEqual(avail_2.json()["availablePlacesByRoom"][self.room3.pk], 2)

        # Availability for 3 guests excludes room3 because only 2 places remain
        avail_3 = c1.get(
            "/api/availability",
            {"start": str(self.start), "end": str(self.end), "guests": 3},
        )
        self.assertNotIn(self.room3.pk, avail_3.json()["roomIds"])

        # Buyer 2 books remaining 2 of 3 places -> 102b and 102c occupied
        c2, t2 = self._guest_client(2)
        r2 = c2.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 2,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t2,
        )
        self.assertEqual(r2.status_code, 201, r2.content)
        b2 = r2.json()
        self.assertEqual(b2["placeLabels"], ["102b", "102c"])
        self.assertEqual(b2["placesCount"], 2)

        # Buyer 3 attempts to book 1 place on overlapping dates -> rejected 409
        c3, t3 = self._guest_client(3)
        r3 = c3.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 1,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t3,
        )
        self.assertEqual(r3.status_code, 409)
        self.assertEqual(r3.json()["code"], "insufficient_places")

    def test_boundary_dates_cancellation_and_hold_expiry_release_places(self):
        c1, t1 = self._guest_client(1)
        # Book all 3 places for [start, end)
        r1 = c1.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 3,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t1,
        )
        self.assertEqual(r1.status_code, 201)
        b1_id = r1.json()["id"]

        # Boundary [end, end + 3) is allowed on the exact same places because stay is [start, end)
        c2, t2 = self._guest_client(2)
        r_next = c2.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.end),
                "end": str(self.end + timedelta(days=3)),
                "guests": 3,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t2,
        )
        self.assertEqual(r_next.status_code, 201, r_next.content)

        # Cancel b1 -> allocations transition to cancelled, freeing [start, end)
        cancel_res = c1.patch(
            f"/api/my-bookings/{b1_id}",
            {"status": "cancelled", "version": 1},
            format="json",
            HTTP_X_CSRFTOKEN=t1,
        )
        self.assertEqual(cancel_res.status_code, 200)
        self.assertTrue(
            all(
                s == "cancelled"
                for s in BookingAllocation.objects.filter(booking_id=b1_id).values_list(
                    "status", flat=True
                )
            )
        )

        # Now another guest can book [start, end) and let hold expire
        r_hold = c2.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 3,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t2,
        )
        self.assertEqual(r_hold.status_code, 201)
        b_hold = Booking.objects.get(pk=r_hold.json()["id"])
        Booking.objects.filter(pk=b_hold.pk).update(
            hold_expires_at=timezone.now() - timedelta(minutes=1)
        )

        # Booking on same dates succeeds after hold expiry sweeps expired allocations
        c3, t3 = self._guest_client(3)
        r_after_exp = c3.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 3,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t3,
        )
        self.assertEqual(r_after_exp.status_code, 201, r_after_exp.content)
        b_hold.refresh_from_db()
        self.assertEqual(b_hold.status, "expired")
        self.assertTrue(
            all(
                s == "expired"
                for s in BookingAllocation.objects.filter(booking=b_hold).values_list(
                    "status", flat=True
                )
            )
        )

    def test_pricing_invariant_not_multiplied_twice_by_allocations_and_under_two_exemption(self):
        # 2 adults + 1 infant (age 1, free under tariff.children_under_two_free) = 3 places, 2 chargeable
        # 7 nights * 20,000 KZT * 2 chargeable = 280,000 KZT base
        # 10% commission -> onlineAmount = 28,000, onsiteAmount = 280,000, total = 308,000 KZT
        c1, t1 = self._guest_client(1)
        infant_dob = str(self.start - timedelta(days=400))  # age 1 at check-in
        res = c1.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 3,
                "childrenBirthDates": [infant_dob],
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t1,
        )
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        self.assertEqual(data["placesCount"], 3)
        self.assertEqual(len(data["placeIds"]), 3)
        self.assertEqual(data["total"], 280000)
        self.assertEqual(data["paymentTerms"]["onsiteAmount"], 280000)
        self.assertEqual(data["paymentTerms"]["onlineAmount"], 28000)
        self.assertEqual(data["paymentTerms"]["total"], 308000)

        # Pay demo and verify voucher includes placeLabels without altering frozen amounts
        pay = c1.post(
            "/api/payments/demo",
            {"bookingId": data["id"], "requestId": str(uuid.uuid4()), "outcome": "success"},
            format="json",
            HTTP_X_CSRFTOKEN=t1,
        )
        self.assertEqual(pay.status_code, 200, pay.content)
        booking = Booking.objects.get(pk=data["id"])
        self.assertEqual(booking.status, "confirmed")
        self.assertTrue(
            all(
                s == "confirmed"
                for s in BookingAllocation.objects.filter(booking=booking).values_list(
                    "status", flat=True
                )
            )
        )
        v_data = voucher_data(booking)
        self.assertEqual(v_data["placeLabels"], ["102a", "102b", "102c"])
        self.assertEqual(v_data["placesCount"], 3)
        self.assertEqual(v_data["paymentTerms"]["total"], 308000)

    def test_planner_endpoint_bounds_and_verify_bed_inventory_command(self):
        sc, st = self._staff_client(self.manager)
        ok = sc.get(
            "/api/planner",
            {
                "resortId": self.resort.pk,
                "start": str(self.start),
                "end": str(self.start + timedelta(days=60)),
            },
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()["days"], 60)

        too_wide = sc.get(
            "/api/planner",
            {
                "resortId": self.resort.pk,
                "start": str(self.start),
                "end": str(self.start + timedelta(days=121)),
            },
        )
        self.assertEqual(too_wide.status_code, 422)

        out = StringIO()
        call_command("verify_bed_inventory", stdout=out)
        self.assertIn('"activeAllocationConflicts": []', out.getvalue())
        self.assertIn('"roomsMissingPlaces": []', out.getvalue())

    def test_staff_notifications_lifecycle_dedup_scope_reassignment_and_accountant_403(self):
        c1, t1 = self._guest_client(1)
        res = c1.post(
            "/api/my-bookings",
            {
                "roomId": self.room3.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 1,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t1,
        )
        self.assertEqual(res.status_code, 201)
        booking_id = res.json()["id"]
        booking = Booking.objects.get(pk=booking_id)

        # Dedup check: calling emit_booking_notification a second time does not duplicate
        from booking.notifications import emit_booking_notification

        emit_booking_notification(booking, "booking_created")
        self.assertEqual(
            StaffNotification.objects.filter(
                booking=booking, kind="booking_created", recipient=self.manager
            ).count(),
            1,
        )

        # Pay booking -> emits booking_paid
        c1.post(
            "/api/payments/demo",
            {"bookingId": booking_id, "requestId": str(uuid.uuid4()), "outcome": "success"},
            format="json",
            HTTP_X_CSRFTOKEN=t1,
        )

        mc, mt = self._staff_client(self.manager)
        n_list = mc.get("/api/staff/notifications")
        self.assertEqual(n_list.status_code, 200)
        self.assertEqual(n_list.json()["unreadCount"], 2)
        items = n_list.json()["items"]
        self.assertEqual({i["kind"] for i in items}, {"booking_created", "booking_paid"})

        # Mark one read
        first_id = items[0]["id"]
        read_res = mc.post(
            f"/api/staff/notifications/{first_id}/read", {}, format="json", HTTP_X_CSRFTOKEN=mt
        )
        self.assertEqual(read_res.status_code, 200)
        self.assertIsNotNone(read_res.json()["readAt"])
        self.assertEqual(mc.get("/api/staff/notifications").json()["unreadCount"], 1)

        # Register and revoke push device; push outbox queued for active device
        dev_res = mc.post(
            "/api/staff/push-devices",
            {
                "platform": "ios",
                "token": "apns-test-device-token-1234567890",
                "deviceLabel": "iPhone 16",
                "appVersion": "1.2.0",
            },
            format="json",
            HTTP_X_CSRFTOKEN=mt,
        )
        self.assertEqual(dev_res.status_code, 201, dev_res.content)
        dev_id = dev_res.json()["id"]
        self.assertEqual(StaffPushDevice.objects.filter(pk=dev_id, is_active=True).count(), 1)

        # Cancel booking -> emits booking_cancelled and creates StaffPushDelivery row
        c1.patch(
            f"/api/my-bookings/{booking_id}",
            {"status": "cancelled", "version": 2},
            format="json",
            HTTP_X_CSRFTOKEN=t1,
        )
        self.assertEqual(
            StaffPushDelivery.objects.filter(
                device_id=dev_id, notification__kind="booking_cancelled"
            ).count(),
            1,
        )

        rev_res = mc.delete(
            f"/api/staff/push-devices/{dev_id}", format="json", HTTP_X_CSRFTOKEN=mt
        )
        self.assertEqual(rev_res.status_code, 200)
        self.assertEqual(rev_res.json()["status"], "revoked")
        self.assertFalse(rev_res.json()["isActive"])

        # Accountant is forbidden from notifications and push-devices
        accountant = User.objects.create_user(
            username="acc@test.tynys",
            email="acc@test.tynys",
            password="StrongPassword123!",
            role="accountant",
            name="Accountant",
        )
        ac, at = self._staff_client(accountant)
        self.assertEqual(ac.get("/api/staff/notifications").status_code, 403)
        self.assertEqual(
            ac.post(
                "/api/staff/push-devices",
                {"platform": "ios", "token": "apns-test-device-token-9999999999"},
                format="json",
                HTTP_X_CSRFTOKEN=at,
            ).status_code,
            403,
        )

        # Reassign resort to another manager -> previous manager immediately loses access to old notifications
        Resort.objects.filter(pk=self.resort.pk).update(account=unrelated_owner())
        self.assertEqual(mc.get("/api/staff/notifications").json()["items"], [])
        self.assertEqual(mc.get("/api/staff/notifications").json()["unreadCount"], 0)
        self.assertEqual(
            mc.post(
                f"/api/staff/notifications/{first_id}/read", {}, format="json", HTTP_X_CSRFTOKEN=mt
            ).status_code,
            403,
        )


class ConcurrentPlaceAllocationTests(TransactionTestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.room2 = Room.objects.create(
            id=f"{self.resort.pk}-205",
            resort=self.resort,
            number="205",
            category="standard",
            title="Двухместный стандарт",
            area=22,
            capacity=2,
            beds="Две кровати",
            price=20000,
            status="active",
        )
        self.start = timezone.localdate() + timedelta(days=10)
        self.end = self.start + timedelta(days=4)

    def test_concurrent_buyers_for_last_remaining_place_never_oversell(self):
        # Occupy 1 of 2 places first
        c0 = APIClient(enforce_csrf_checks=True)
        authenticate_guest(c0, phone="+77019990000", name="Initial Guest")
        t0 = c0.get("/api/auth/csrf").json()["token"]
        r0 = c0.post(
            "/api/my-bookings",
            {
                "roomId": self.room2.pk,
                "tariffId": self.tariff.pk,
                "start": str(self.start),
                "end": str(self.end),
                "guests": 1,
                "requestId": str(uuid.uuid4()),
            },
            format="json",
            HTTP_X_CSRFTOKEN=t0,
        )
        self.assertEqual(r0.status_code, 201, r0.content)

        # Now two concurrent buyers compete for the single remaining place (205b)
        def attempt_booking(idx):
            close_old_connections()
            try:
                client = APIClient(enforce_csrf_checks=True)
                authenticate_guest(
                    client, phone=f"+7701999000{idx}", name=f"Concurrent {idx}"
                )
                token = client.get("/api/auth/csrf").json()["token"]
                res = client.post(
                    "/api/my-bookings",
                    {
                        "roomId": self.room2.pk,
                        "tariffId": self.tariff.pk,
                        "start": str(self.start),
                        "end": str(self.end),
                        "guests": 1,
                        "requestId": str(uuid.uuid4()),
                    },
                    format="json",
                    HTTP_X_CSRFTOKEN=token,
                )
                return res.status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(attempt_booking, 1)
            f2 = pool.submit(attempt_booking, 2)
            statuses = sorted([f1.result(), f2.result()])

        self.assertEqual(statuses, [201, 409])
        active_allocs = BookingAllocation.objects.filter(
            room=self.room2, status__in=["pending", "confirmed"]
        )
        self.assertEqual(active_allocs.count(), 2)
        self.assertEqual(
            len(set(active_allocs.values_list("place_id", flat=True))), 2
        )
