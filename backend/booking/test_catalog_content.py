from django.test import TestCase
from rest_framework.test import APIClient

from booking.test_helpers import unrelated_owner

from .models import Resort
from .serializers import ResortSerializer
from .tests import fixture


class CatalogContentTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.manager)
        self.token = self.client.get("/api/auth/csrf").json()["token"]

    def patch(self, path, data):
        return self.client.patch(path, data, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_owned_content_roundtrip_public_and_clear_without_losing_media(self):
        media = [{"kind": "image", "url": "/assets/resort.jpg", "alt": "Example"}]
        self.resort.media = media
        self.resort.save()
        result = self.patch(
            f"/api/resorts/{self.resort.pk}",
            {
                "version": 1,
                "description": "Before gallery",
                "descriptionAfter": "After gallery\nSecond paragraph",
                "staffWhatsApp": "77000000001",
                "twoGisUrl": "https://2gis.kz/almaty/firm/123",
            },
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["staffWhatsApp"], "+77000000001")
        self.assertEqual(result.json()["media"], media)
        room = self.patch(
            f"/api/rooms/{self.room.pk}",
            {
                "version": 1,
                "description": "Room before",
                "descriptionAfter": "Room after",
            },
        )
        self.assertEqual(room.status_code, 200, room.content)
        public = APIClient().get(f"/api/resorts/{self.resort.pk}").json()
        self.assertEqual(public["resort"]["descriptionAfter"], "After gallery\nSecond paragraph")
        public_room = APIClient().get(f"/api/rooms/{self.room.pk}").json()
        self.assertEqual(public_room["room"]["descriptionAfter"], "Room after")
        self.assertEqual(public_room["resort"]["twoGisUrl"], "https://2gis.kz/almaty/firm/123")
        cleared = self.patch(
            f"/api/resorts/{self.resort.pk}",
            {
                "version": 2,
                "descriptionAfter": "",
                "staffWhatsApp": "",
                "twoGisUrl": "",
            },
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["description"], "Before gallery")
        self.assertEqual(cleared.json()["descriptionAfter"], "")

    def test_contact_validation_blocks_foreign_hosts_and_unsafe_urls(self):
        for value in [
            "http://2gis.kz/almaty",
            "https://2gis.kz.evil.test/",
            "https://evil.test/",
            "https://user:pass@2gis.kz/",
            "javascript:alert(1)",
            "https://2gis.kz:444/",
            "https://2gis.kz\\@evil.test/",
            "https://2gis.kz/\npath",
        ]:
            with self.subTest(value=value):
                serializer = ResortSerializer(self.resort, data={"twoGisUrl": value}, partial=True)
                self.assertFalse(serializer.is_valid())
        for value in ["+77000000001", "77000000001", ""]:
            serializer = ResortSerializer(self.resort, data={"staffWhatsApp": value}, partial=True)
            self.assertTrue(serializer.is_valid(), serializer.errors)
        for value in ["123", "+00000000000", "https://wa.me/77000000001", "77000000001?x=1"]:
            serializer = ResortSerializer(self.resort, data={"staffWhatsApp": value}, partial=True)
            self.assertFalse(serializer.is_valid())

    def test_manager_cannot_change_foreign_contacts_or_descriptions(self):
        foreign = Resort.objects.create(
            account=unrelated_owner(),
            name="Other",
            city="Example",
            address="Example",
            lat=41,
            lng=69,
        )
        response = self.patch(
            f"/api/resorts/{foreign.pk}",
            {
                "version": 1,
                "descriptionAfter": "Overwrite",
                "staffWhatsApp": "+77000000001",
            },
        )
        self.assertEqual(response.status_code, 403)
        foreign.refresh_from_db()
        self.assertEqual(foreign.description_after, "")
        self.assertEqual(foreign.staff_whatsapp, "")

    def test_staff_price_periods_are_public_without_http_cache(self):
        periods = [{"label": "Season", "start": "2030-06-01", "end": "2030-07-01", "price": 25000}]
        saved = self.patch(f"/api/rooms/{self.room.pk}", {"version": 1, "pricePeriods": periods})
        self.assertEqual(saved.status_code, 200, saved.content)
        public = APIClient()
        for path, kind in [
            (f"/api/rooms/{self.room.pk}", "room"),
            (f"/api/resorts/{self.resort.pk}", "rooms"),
            ("/api/catalog", "rooms"),
        ]:
            response = public.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response.headers["Cache-Control"])
            data = response.json()
            room = (
                data[kind]
                if kind == "room"
                else next(r for r in data[kind] if r["id"] == self.room.pk)
            )
            self.assertEqual(room["pricePeriods"], periods)
