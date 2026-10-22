import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Audit, Booking, Resort, Room, Tariff, User

PASSWORD = "Test-only-forest-9284!"


def fixture():
    resort = Resort.objects.create(
        name="Тестовый санаторий",
        city="Сарыагаш",
        address="Тест",
        lat=41,
        lng=69,
        status="published",
    )
    room = Room.objects.create(
        resort=resort,
        number="201",
        category="standard",
        title="Стандарт",
        area=20,
        capacity=2,
        beds="2",
        price=18000,
    )
    tariff = Tariff.objects.create(resort=resort, name="Питание", supplement=4500)
    manager = User.objects.create_user(
        username="manager@example.test",
        email="manager@example.test",
        name="Управляющий",
        password=PASSWORD,
        resort=resort,
    )
    administrator = User.objects.create_user(
        username="admin@example.test", email="admin@example.test", password=PASSWORD, role="admin"
    )
    return resort, room, tariff, manager, administrator


class ApiTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        self.start = timezone.localdate() + timedelta(days=5)
        self.data = {
            "roomId": self.room.pk,
            "tariffId": self.tariff.pk,
            "start": str(self.start),
            "end": str(self.start + timedelta(days=3)),
            "guests": 2,
            "guestLabel": "Тестовый гость",
            "guestPhone": "+70000000000",
            "requestId": str(uuid.uuid4()),
        }

    def write(self, method, path, data=None):
        return getattr(self.client, method)(
            path, data or {}, format="json", HTTP_X_CSRFTOKEN=self.token
        )

    def staff(self, user=None):
        self.client.force_login(user or self.manager)
        self.token = self.client.get("/api/auth/csrf").json()["token"]

    def create(self):
        response = self.write("post", "/api/my-bookings", self.data)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_login_password_and_logout(self):
        self.assertEqual(self.client.get("/api/auth/session").status_code, 204)
        self.assertEqual(
            self.write("post", "/api/auth/login", {"accountId": "admin"}).status_code, 401
        )
        result = self.write(
            "post", "/api/auth/login", {"email": self.manager.email, "password": PASSWORD}
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["role"], "manager")
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        self.assertEqual(self.write("post", "/api/auth/logout").status_code, 204)
        self.assertEqual(self.client.get("/api/workspace").status_code, 401)

    def test_csrf_required_for_guest_and_login(self):
        self.assertEqual(
            self.client.post("/api/my-bookings", self.data, format="json").status_code, 403
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                {"email": self.manager.email, "password": PASSWORD},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(Booking.objects.count(), 0)

    def test_pending_price_idempotency_and_confirmation(self):
        booking = self.create()
        self.assertEqual(booking["status"], "pending")
        self.assertEqual(booking["total"], 81000)
        self.assertEqual(self.create()["id"], booking["id"])
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Audit.objects.count(), 1)
        self.staff()
        response = self.write(
            "patch", "/api/bookings/" + booking["id"], {"status": "confirmed", "version": 1}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "confirmed")
        self.assertEqual(Audit.objects.count(), 2)
        self.assertNotIn("guestPhone", Audit.objects.last().after)

    def test_pending_blocks_and_rejection_releases(self):
        b = self.create()
        self.data["requestId"] = str(uuid.uuid4())
        self.assertEqual(self.write("post", "/api/my-bookings", self.data).status_code, 409)
        available = self.client.get(
            "/api/availability", {"start": self.data["start"], "end": self.data["end"], "guests": 2}
        ).json()
        self.assertNotIn(self.room.pk, available["roomIds"])
        self.staff()
        self.assertEqual(
            self.write(
                "patch", "/api/bookings/" + b["id"], {"status": "rejected", "version": 1}
            ).status_code,
            200,
        )
        self.create()

    def test_checkout_adjacent_allowed(self):
        self.create()
        self.data.update(
            start=self.data["end"],
            end=str(self.start + timedelta(days=6)),
            requestId=str(uuid.uuid4()),
        )
        self.create()

    def test_guest_cannot_confirm_or_see_other_session(self):
        b = self.create()
        self.assertEqual(
            self.write(
                "patch", "/api/my-bookings/" + b["id"], {"status": "confirmed", "version": 1}
            ).status_code,
            409,
        )
        other = APIClient(enforce_csrf_checks=True)
        token = other.get("/api/auth/csrf").json()["token"]
        self.assertEqual(other.get("/api/my-bookings").json(), [])
        self.assertEqual(
            other.patch(
                "/api/my-bookings/" + b["id"],
                {"status": "cancelled", "version": 1},
                format="json",
                HTTP_X_CSRFTOKEN=token,
            ).status_code,
            404,
        )

    def test_tenant_scope_and_admin_only(self):
        other = Resort.objects.create(name="Другой", city="Тест", address="Тест", lat=40, lng=70)
        self.staff()
        workspace = self.client.get("/api/workspace").json()
        self.assertEqual([r["id"] for r in workspace["resorts"]], [self.resort.pk])
        self.assertEqual(workspace["accounts"], [])
        self.assertEqual(
            self.write(
                "patch", "/api/resorts/" + other.pk, {"version": 1, "name": "Взлом"}
            ).status_code,
            403,
        )
        self.assertEqual(self.write("post", "/api/resorts", {}).status_code, 403)
        self.assertEqual(self.write("post", "/api/accounts", {}).status_code, 403)

    def test_staff_booking_not_guest_owned(self):
        self.staff()
        result = self.write("post", "/api/bookings", self.data)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()["status"], "pending")
        self.assertEqual(self.client.get("/api/my-bookings").json(), [])

    def test_stale_version_and_invalid_transition(self):
        b = self.create()
        self.staff()
        url = "/api/bookings/" + b["id"]
        self.assertEqual(
            self.write("patch", url, {"status": "confirmed", "version": 0}).status_code, 409
        )
        self.assertEqual(
            self.write("patch", url, {"status": "confirmed", "version": 1}).status_code, 200
        )
        self.assertEqual(
            self.write("patch", url, {"status": "rejected", "version": 2}).status_code, 409
        )
        self.assertEqual(
            self.write("patch", url, {"status": "cancelled", "version": 2}).status_code, 200
        )
        self.assertEqual(
            self.write("patch", url, {"status": "confirmed", "version": 3}).status_code, 409
        )

    def test_validation_and_server_price(self):
        self.data["guests"] = 3
        self.assertEqual(self.write("post", "/api/my-bookings", self.data).status_code, 422)
        self.data["guests"] = 2
        self.data["end"] = self.data["start"]
        self.assertEqual(self.write("post", "/api/my-bookings", self.data).status_code, 422)
        self.data["end"] = str(self.start + timedelta(days=3))
        self.data["total"] = 1
        self.assertEqual(self.create()["total"], 81000)

    def test_db_constraint_independent_of_api(self):
        b = Booking.objects.get(pk=self.create()["id"])
        b.pk, b.request_key = str(uuid.uuid4()), uuid.uuid4()
        with self.assertRaises(IntegrityError), transaction.atomic():
            b.save(force_insert=True)

    def test_reference_protection_and_history_atomicity(self):
        self.create()
        self.staff()
        count = Audit.objects.count()
        self.assertEqual(
            self.write("delete", "/api/rooms/" + self.room.pk, {"version": 1}).status_code, 409
        )
        self.assertEqual(Audit.objects.count(), count)
        self.assertEqual(
            self.write(
                "patch", "/api/rooms/" + self.room.pk, {"version": 1, "capacity": 1}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.write(
                "patch", "/api/rooms/" + self.room.pk, {"version": 1, "status": "maintenance"}
            ).status_code,
            409,
        )
        self.staff(self.admin)
        self.assertEqual(
            self.write("delete", "/api/resorts/" + self.resort.pk, {"version": 1}).status_code, 409
        )

    def test_catalog_crud_publish_archive(self):
        self.staff(self.admin)
        result = self.write(
            "post",
            "/api/resorts",
            {
                "name": "Новый",
                "city": "Тест",
                "address": "Тест",
                "lat": 42,
                "lng": 69,
                "status": "draft",
            },
        )
        self.assertEqual(result.status_code, 201, result.content)
        r = result.json()
        self.assertEqual(
            self.write(
                "patch", "/api/resorts/" + r["id"], {"version": 1, "status": "published"}
            ).status_code,
            422,
        )
        room = self.write(
            "post",
            "/api/rooms",
            {
                "resortId": r["id"],
                "number": "1",
                "category": "standard",
                "title": "Тест",
                "area": 20,
                "capacity": 2,
                "beds": "2",
                "price": 100,
                "status": "active",
            },
        )
        self.assertEqual(room.status_code, 201, room.content)
        tariff = self.write(
            "post",
            "/api/tariffs",
            {
                "resortId": r["id"],
                "name": "Тест",
                "description": "",
                "supplement": 0,
                "features": "Питание\nБассейн",
                "status": "active",
            },
        )
        self.assertEqual(tariff.status_code, 201)
        self.assertEqual(
            self.write(
                "patch", "/api/resorts/" + r["id"], {"version": 1, "status": "published"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.write("delete", "/api/resorts/" + r["id"], {"version": 2}).status_code, 200
        )
        self.assertEqual(self.write("post", "/api/tariffs", {"resortId": r["id"]}).status_code, 409)

    def test_manager_account_password_and_disable(self):
        self.staff(self.admin)
        data = {
            "name": "Новый",
            "login": "new@example.test",
            "resortId": self.resort.pk,
            "status": "active",
            "password": PASSWORD,
        }
        result = self.write("post", "/api/accounts", data)
        self.assertEqual(result.status_code, 201, result.content)
        self.assertNotIn("password", result.json())
        user = User.objects.get(email=data["login"])
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        other = APIClient()
        other.force_login(user)
        data.update(status="disabled", version=1)
        self.assertEqual(
            self.write("patch", "/api/accounts/" + str(user.pk), data).status_code, 200
        )
        self.assertEqual(other.get("/api/workspace").status_code, 401)

    def test_price_snapshot_survives_change(self):
        b = self.create()
        self.staff()
        self.assertEqual(
            self.write(
                "patch", "/api/rooms/" + self.room.pk, {"price": 999, "version": 1}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/workspace").json()["bookings"][0]["total"], b["total"]
        )

    def test_idempotency_key_cannot_change_request(self):
        self.create()
        self.data["guests"] = 1
        self.assertEqual(self.write("post", "/api/my-bookings", self.data).status_code, 409)

    def test_private_cache_and_malformed_account_id(self):
        self.staff(self.admin)
        response = self.client.get("/api/workspace")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.write("patch", "/api/accounts/not-an-id", {}).status_code, 404)

    def test_login_rate_limit_is_shared_in_database(self):
        import hashlib

        from .models import LoginAttempt

        key = hashlib.sha256(("email:" + self.manager.email).encode()).hexdigest()
        LoginAttempt.objects.create(key=key, count=30, since=timezone.now())
        result = self.write(
            "post", "/api/auth/login", {"email": self.manager.email, "password": PASSWORD}
        )
        self.assertEqual(result.status_code, 429)

    def test_coordinates_and_account_validation(self):
        self.staff(self.admin)
        self.assertEqual(
            self.write(
                "patch", "/api/resorts/" + self.resort.pk, {"version": 1, "lat": "NaN"}
            ).status_code,
            422,
        )
        data = {
            "name": "Тест",
            "login": self.manager.email,
            "resortId": self.resort.pk,
            "status": "active",
            "password": PASSWORD,
        }
        self.assertEqual(self.write("post", "/api/accounts", data).status_code, 422)
        data["login"] = "another@example.test"
        data["password"] = "123456789012"
        self.assertEqual(self.write("post", "/api/accounts", data).status_code, 422)


class ConcurrencyTests(TransactionTestCase):
    def test_simultaneous_requests_one_wins(self):
        resort, room, tariff, manager, administrator = fixture()
        start = timezone.localdate() + timedelta(days=8)
        barrier = Barrier(2)

        def reserve():
            close_old_connections()
            try:
                client = APIClient(enforce_csrf_checks=True)
                token = client.get("/api/auth/csrf").json()["token"]
                barrier.wait(timeout=10)
                return client.post(
                    "/api/my-bookings",
                    {
                        "roomId": room.pk,
                        "tariffId": tariff.pk,
                        "start": str(start),
                        "end": str(start + timedelta(days=2)),
                        "guests": 1,
                        "guestLabel": "Гость",
                        "guestPhone": "+70000000000",
                        "requestId": str(uuid.uuid4()),
                    },
                    format="json",
                    HTTP_X_CSRFTOKEN=token,
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: reserve(), range(2)))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Audit.objects.count(), 1)
