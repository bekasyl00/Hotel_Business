import io
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from psycopg.types.range import Range
from rest_framework.test import APIClient

from .models import Audit, Booking, MediaAsset, Resort, Review
from .tests import fixture


class CatalogueTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf").json()["token"]

    def write(self, method, path, data):
        return getattr(self.client, method)(path, data, format="json", HTTP_X_CSRFTOKEN=self.token)

    def staff(self, user=None):
        self.client.force_login(user or self.manager)
        self.token = self.client.get("/api/auth/csrf").json()["token"]

    def completed_booking(self):
        end = timezone.localdate() - timedelta(days=1)
        return Booking.objects.create(
            resort=self.resort,
            room=self.room,
            tariff=self.tariff,
            stay=Range(end - timedelta(days=3), end, bounds="[)"),
            guests=1,
            guest_label="Private guest",
            guest_phone="+70000000000",
            owner=self.client.session["guest_owner"],
            status="confirmed",
            source="website",
            request_key=uuid.uuid4(),
            request_hash="a" * 64,
        )

    def test_catalogue_fields_and_public_detail_hides_drafts(self):
        self.staff()
        response = self.write(
            "patch",
            f"/api/resorts/{self.resort.pk}",
            {
                "version": 1,
                "category": "family",
                "resortClass": "premium",
                "checkInTime": "15:30",
                "timeZone": "Asia/Almaty",
                "amenities": ["Бассейн"],
                "media": [{"kind": "image", "url": "/assets/resort.jpg", "alt": "Фото"}],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["checkInTime"], "15:30")
        self.client.logout()
        result = self.client.get(f"/api/resorts/{self.resort.pk}").json()
        self.assertEqual(result["resort"]["category"], "family")
        self.assertEqual(result["rooms"][0]["id"], self.room.pk)
        self.assertNotIn("bookings", result)
        self.assertEqual(self.client.get(f"/api/rooms/{self.room.pk}").status_code, 200)
        self.assertEqual(len(self.client.get("/api/categories").json()), 4)
        self.resort.status = "draft"
        self.resort.save()
        self.assertEqual(self.client.get(f"/api/resorts/{self.resort.pk}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/rooms/{self.room.pk}").status_code, 404)

    def test_media_urls_timezone_and_discount_validation(self):
        self.staff()
        for url in [
            "javascript:alert(1)",
            "//evil.test/x.jpg",
            "/media/../secret",
            "file:///tmp/file",
            "http://example.test/photo.jpg",
            "https://[bad",
            "https://user:pass@example.test/photo.jpg",
        ]:
            self.assertEqual(
                self.write(
                    "patch",
                    f"/api/resorts/{self.resort.pk}",
                    {"version": 1, "media": [{"kind": "image", "url": url}]},
                ).status_code,
                422,
            )
        self.assertEqual(
            self.write(
                "patch", f"/api/resorts/{self.resort.pk}", {"version": 1, "timeZone": "Not/AZone"}
            ).status_code,
            422,
        )
        for payload in [
            {"priceKind": "regular", "discountPercent": 10},
            {"priceKind": "discount", "discountPercent": 91},
            {"priceKind": "discount", "discountPercent": 0},
        ]:
            self.assertEqual(
                self.write(
                    "patch", f"/api/tariffs/{self.tariff.pk}", {"version": 1, **payload}
                ).status_code,
                422,
            )
        response = self.write(
            "patch",
            f"/api/tariffs/{self.tariff.pk}",
            {"version": 1, "priceKind": "discount", "discountPercent": 15},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["discountPercent"], 15)

    def test_review_requires_completed_own_booking_and_unique_stay(self):
        booking = self.completed_booking()
        payload = {
            "bookingId": booking.id,
            "rating": 5,
            "text": "Хороший отдых в санатории",
            "photos": ["/assets/resort.jpg"],
        }
        foreign = APIClient()
        self.assertEqual(foreign.post("/api/reviews", payload, format="json").status_code, 404)
        booking.status = "pending"
        booking.save()
        self.assertEqual(self.write("post", "/api/reviews", payload).status_code, 409)
        booking.status = "confirmed"
        booking.save()
        response = self.write("post", "/api/reviews", payload)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], "pending")
        self.assertEqual(self.write("post", "/api/reviews", payload).status_code, 409)
        self.assertEqual(self.client.get("/api/reviews", {"resortId": self.resort.pk}).json(), [])
        self.assertEqual(Audit.objects.filter(entity="reviews").count(), 1)

    def test_future_stay_and_staff_cannot_review(self):
        booking = self.completed_booking()
        end = timezone.localdate() + timedelta(days=3)
        booking.stay = Range(end - timedelta(days=2), end, bounds="[)")
        booking.save()
        payload = {"bookingId": booking.id, "rating": 5, "text": "Хороший отдых в санатории"}
        self.assertEqual(self.write("post", "/api/reviews", payload).status_code, 409)
        self.staff()
        self.assertEqual(self.write("post", "/api/reviews", payload).status_code, 403)

    def test_moderation_scope_versions_public_privacy_and_rating(self):
        booking = self.completed_booking()
        review = Review.objects.create(
            resort=self.resort, booking=booking, rating=4, text="Текст отзыва после проживания"
        )
        foreign_resort = Resort.objects.create(
            name="Другой", city="Тест", address="Тест", lat=1, lng=1
        )
        self.manager.resort = foreign_resort
        self.manager.save()
        self.staff()
        self.assertEqual(self.client.get("/api/workspace").json()["reviews"], [])
        self.assertEqual(
            self.write(
                "patch", f"/api/reviews/{review.id}", {"version": 1, "status": "approved"}
            ).status_code,
            403,
        )
        self.manager.resort = self.resort
        self.manager.save()
        response = self.write(
            "patch",
            f"/api/reviews/{review.id}",
            {"version": 1, "status": "approved", "reply": "Спасибо за отзыв"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.write(
                "patch", f"/api/reviews/{review.id}", {"version": 1, "status": "rejected"}
            ).status_code,
            409,
        )
        public = self.client.get("/api/reviews", {"resortId": self.resort.pk}).json()[0]
        self.assertEqual(public["reply"], "Спасибо за отзыв")
        self.assertNotIn("bookingId", public)
        self.assertNotIn("guestPhone", public)
        self.assertNotIn("owner", public)
        self.resort.refresh_from_db()
        self.assertEqual(self.resort.rating, 4)
        catalogue = self.client.get("/api/catalog").json()["resorts"][0]
        self.assertEqual(catalogue["reviewCount"], 1)
        self.assertEqual(catalogue["reviewRating"], 4)
        self.assertEqual(
            self.write(
                "patch", f"/api/reviews/{review.id}", {"version": 2, "status": "rejected"}
            ).status_code,
            200,
        )
        self.resort.refresh_from_db()
        self.assertEqual(self.resort.rating, 0)
        catalogue = self.client.get("/api/catalog").json()["resorts"][0]
        self.assertEqual(catalogue["reviewCount"], 0)
        self.assertIsNone(catalogue["reviewRating"])

    def test_upload_decodes_images_and_checks_scope(self):
        image = io.BytesIO()
        Image.new("RGB", (12, 12), "green").save(image, "PNG")
        self.staff()
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            upload = SimpleUploadedFile(
                "untrusted-name.png", image.getvalue(), content_type="image/png"
            )
            response = self.client.post(
                "/api/media",
                {"resortId": self.resort.pk, "file": upload},
                format="multipart",
                HTTP_X_CSRFTOKEN=self.token,
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(response.json()["kind"], "image")
            self.assertEqual(
                response.json()["url"], MediaAsset.objects.get(pk=response.json()["id"]).url
            )
            self.assertTrue(
                MediaAsset.objects.get(pk=response.json()["id"]).storage_key.endswith(".jpg")
            )
            fake = SimpleUploadedFile("fake.png", b"<script>bad</script>", content_type="image/png")
            self.assertEqual(
                self.client.post(
                    "/api/media",
                    {"resortId": self.resort.pk, "file": fake},
                    format="multipart",
                    HTTP_X_CSRFTOKEN=self.token,
                ).status_code,
                422,
            )
            other = Resort.objects.create(name="Другой", city="Тест", address="Тест", lat=1, lng=1)
            upload = SimpleUploadedFile("photo.png", image.getvalue(), content_type="image/png")
            self.assertEqual(
                self.client.post(
                    "/api/media",
                    {"resortId": other.pk, "file": upload},
                    format="multipart",
                    HTTP_X_CSRFTOKEN=self.token,
                ).status_code,
                403,
            )

    def test_guest_upload_requires_eligible_booking(self):
        image = io.BytesIO()
        Image.new("RGB", (12, 12)).save(image, "JPEG")
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            upload = SimpleUploadedFile("photo.jpg", image.getvalue(), content_type="image/jpeg")
            self.assertEqual(
                self.client.post(
                    "/api/media",
                    {"bookingId": "missing", "file": upload},
                    format="multipart",
                    HTTP_X_CSRFTOKEN=self.token,
                ).status_code,
                404,
            )
            booking = self.completed_booking()
            upload = SimpleUploadedFile("photo.jpg", image.getvalue(), content_type="image/jpeg")
            response = self.client.post(
                "/api/media",
                {"bookingId": booking.pk, "file": upload},
                format="multipart",
                HTTP_X_CSRFTOKEN=self.token,
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertIn("/api/media/files/", response.json()["url"])
            self.assertNotIn(booking.pk, response.json()["url"])

    def test_upload_requires_csrf_and_strips_original_filename_and_metadata(self):
        self.staff()
        image = io.BytesIO()
        exif = Image.Exif()
        exif[315] = "Private author metadata"
        Image.new("RGB", (12, 12)).save(image, "JPEG", exif=exif)
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            upload = SimpleUploadedFile(
                "guest-identity.jpg", image.getvalue(), content_type="image/jpeg"
            )
            self.assertEqual(
                self.client.post(
                    "/api/media", {"resortId": self.resort.pk, "file": upload}, format="multipart"
                ).status_code,
                403,
            )
            self.assertEqual(list(Path(folder).rglob("*.jpg")), [])
            upload = SimpleUploadedFile(
                "guest-identity.jpg", image.getvalue(), content_type="image/jpeg"
            )
            response = self.client.post(
                "/api/media",
                {"resortId": self.resort.pk, "file": upload},
                format="multipart",
                HTTP_X_CSRFTOKEN=self.token,
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertNotIn("guest-identity", response.json()["url"])
            saved = list(Path(folder).rglob("*.jpg"))
            self.assertEqual(len(saved), 1)
            with Image.open(saved[0]) as stored:
                self.assertEqual(dict(stored.getexif()), {})

    def test_review_creation_requires_csrf(self):
        booking = self.completed_booking()
        response = self.client.post(
            "/api/reviews",
            {"bookingId": booking.pk, "rating": 5, "text": "Текст отзыва после проживания"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Review.objects.exists())
