import io
import tempfile
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from .models import GuestAccount, GuestProfile, MediaAsset, Resort
from .tests import PASSWORD, fixture


def photo():
    output = io.BytesIO()
    Image.new("RGB", (40, 40), "#359780").save(output, "PNG")
    return SimpleUploadedFile("private-original.png", output.getvalue(), content_type="image/png")


class ManagedMediaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.resort, cls.room, cls.tariff, cls.manager, cls.admin = fixture()
        cls.profile = GuestProfile.objects.create(
            owner="avatar-test-owner", name="Демо гость", phone="+77010000031"
        )
        cls.account = GuestAccount.objects.create(
            profile=cls.profile, phone=cls.profile.phone, password=make_password(PASSWORD)
        )

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.override = override_settings(MEDIA_ROOT=folder.name, MEDIA_STORAGE="local")
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.staff = APIClient(enforce_csrf_checks=True)
        self.staff.force_login(self.manager)
        self.csrf = self.staff.get("/api/auth/csrf").json()["token"]
        self.guest = APIClient(enforce_csrf_checks=True)
        result = self.guest.post(
            "/api/v1/mobile-auth/login",
            {
                "phone": self.profile.phone,
                "password": PASSWORD,
                "deviceName": "Media test",
            },
            format="json",
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.guest.credentials(HTTP_AUTHORIZATION="Bearer " + result.json()["accessToken"])

    def upload(self):
        response = self.staff.post(
            "/api/media",
            {"resortId": self.resort.pk, "file": photo()},
            format="multipart",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_catalogue_file_becomes_public_only_when_attached_to_published_content(self):
        data = self.upload()
        self.assertEqual(APIClient().get(data["url"]).status_code, 404)
        self.assertEqual(self.staff.get(data["url"]).status_code, 200)
        response = self.staff.patch(
            "/api/resorts/" + self.resort.pk,
            {
                "version": self.resort.version,
                "media": [data],
            },
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 200, response.content)
        public = APIClient().get(data["url"])
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public["Content-Type"], "image/jpeg")
        self.assertEqual(public["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", public["Cache-Control"])
        self.assertTrue(b"".join(public.streaming_content).startswith(b"\xff\xd8"))
        self.resort.status = "draft"
        self.resort.save(update_fields=["status"])
        self.assertEqual(APIClient().get(data["url"]).status_code, 404)

    def test_cross_tenant_cannot_read_or_attach_asset(self):
        data = self.upload()
        other = Resort.objects.create(name="Other", city="Test", address="Test", lat=1, lng=1)
        self.manager.resort = other
        self.manager.save(update_fields=["resort"])
        self.assertEqual(self.staff.get(data["url"]).status_code, 404)
        response = self.staff.patch(
            "/api/resorts/" + other.pk,
            {"version": 1, "media": [data]},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "media_scope_invalid")

    def test_managed_asset_aliases_cannot_bypass_ownership_or_reference_tracking(self):
        data = self.upload()
        for alias in [
            data["url"].replace("/media/", "/%6dedia/"),
            data["url"].replace("/api/", "/%61pi/"),
            "https://example.invalid" + data["url"],
        ]:
            with self.subTest(alias=alias):
                response = self.staff.patch(
                    "/api/resorts/" + self.resort.pk,
                    {
                        "version": self.resort.version,
                        "media": [{**data, "url": alias}],
                    },
                    format="json",
                    HTTP_X_CSRFTOKEN=self.csrf,
                )
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "media_scope_invalid")
        self.resort.refresh_from_db()
        self.assertEqual(self.resort.media, [])

    def test_avatar_native_upload_replace_delete_and_owner_checks(self):
        response = self.guest.post("/api/v1/profile/avatar", {"file": photo()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.content)
        url = response.json()["profile"]["avatarUrl"]
        self.assertEqual(self.guest.get(url).status_code, 200)
        self.assertEqual(APIClient().get(url).status_code, 404)
        self.assertEqual(self.staff.get(url).status_code, 404)  # No scoped booking exists.
        self.assertEqual(self.guest.get("/api/profile").json()["profile"]["avatarUrl"], url)
        replacement = self.guest.post("/api/profile/avatar", {"file": photo()}, format="multipart")
        next_url = replacement.json()["profile"]["avatarUrl"]
        self.assertNotEqual(url, next_url)
        self.assertEqual(self.guest.get(url).status_code, 404)
        removed = self.guest.delete("/api/profile/avatar")
        self.assertEqual(removed.status_code, 200)
        self.assertIsNone(removed.json()["profile"]["avatarUrl"])
        self.assertEqual(self.guest.get(next_url).status_code, 404)

    def test_anonymous_avatar_and_forged_image_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf").json()["token"]
        denied = client.post(
            "/api/profile/avatar", {"file": photo()}, format="multipart", HTTP_X_CSRFTOKEN=csrf
        )
        self.assertEqual(denied.status_code, 401)
        denied_csrf = client.post("/api/profile/avatar", {"file": photo()}, format="multipart")
        self.assertEqual(denied_csrf.status_code, 403)
        fake = SimpleUploadedFile("fake.png", b"<script>bad</script>", content_type="image/png")
        self.assertEqual(
            self.guest.post("/api/profile/avatar", {"file": fake}, format="multipart").status_code,
            422,
        )
        self.assertEqual(MediaAsset.objects.count(), 0)

    def test_private_files_support_ranges_and_head(self):
        data = self.upload()
        asset = MediaAsset.objects.get(pk=data["id"])
        response = self.staff.get(data["url"], HTTP_RANGE="bytes=0-9")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(b"".join(response.streaming_content)), 10)
        self.assertEqual(response["Content-Range"], f"bytes 0-9/{asset.size}")
        self.assertEqual(self.staff.get(data["url"], HTTP_RANGE="bytes=99999999-").status_code, 416)
        self.assertEqual(
            self.staff.get(data["url"], HTTP_RANGE="bytes=0-" + "9" * 4500).status_code, 416
        )
        head = self.staff.head(data["url"])
        self.assertEqual(int(head["Content-Length"]), asset.size)
        self.assertEqual(head.content, b"")

    @override_settings(MEDIA_GUEST_DAILY_BYTES=1)
    def test_quota_prevents_writes(self):
        response = self.guest.post("/api/profile/avatar", {"file": photo()}, format="multipart")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(MediaAsset.objects.count(), 0)

    def test_cleanup_preserves_referenced_assets_and_dry_run(self):
        unused = self.upload()
        kept = self.upload()
        self.room.media = [{"kind": "image", "url": kept["url"], "alt": ""}]
        self.room.save(update_fields=["media"])
        MediaAsset.objects.update(created_at=timezone.now() - timedelta(days=2))
        out = io.StringIO()
        call_command("cleanup_media", stdout=out)
        self.assertIn("Would delete 1", out.getvalue())
        self.assertEqual(MediaAsset.objects.count(), 2)
        key = MediaAsset.objects.get(pk=unused["id"]).storage_key
        call_command("cleanup_media", delete=True, stdout=io.StringIO())
        self.assertFalse(default_storage.exists(key))
        self.assertEqual(list(MediaAsset.objects.values_list("pk", flat=True)), [kept["id"]])
