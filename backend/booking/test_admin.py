import hashlib
import uuid
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from psycopg.types.range import Range

from commerce.models import DemoPayment, DemoRefund

from .admin import platform_admin_site
from .models import (
    Audit,
    Booking,
    GuestAccount,
    GuestChallenge,
    GuestProfile,
    LoginAttempt,
    MediaAsset,
    Review,
)
from .tests import PASSWORD, fixture


@override_settings(STAFF_WORKSPACE_URL="https://staff.example.test/staff")
class PlatformAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.resort, cls.room, cls.tariff, cls.manager, cls.operator = fixture()
        cls.operator.is_staff = True
        cls.operator.is_superuser = True
        cls.operator.save()
        cls.manager.is_staff = True
        cls.manager.save()
        cls.profile = GuestProfile.objects.create(
            owner="private-owner-should-never-be-rendered",
            name="Демо гость",
            phone="+77000000000",
        )
        cls.guest = GuestAccount.objects.create(
            phone=cls.profile.phone, profile=cls.profile, password=make_password(PASSWORD)
        )
        cls.asset = MediaAsset.objects.create(
            purpose="avatar",
            kind="image",
            storage_key="private/avatar/hidden-storage-key.jpg",
            size=100,
            content_type="image/jpeg",
            profile=cls.profile,
        )
        cls.profile.avatar = cls.asset
        cls.profile.save(update_fields=["avatar"])
        start = timezone.localdate() + timedelta(days=5)
        cls.booking = Booking.objects.create(
            resort=cls.resort,
            room=cls.room,
            tariff=cls.tariff,
            stay=Range(start, start + timedelta(days=2), bounds="[)"),
            guests=1,
            guest_label=cls.profile.name,
            guest_phone=cls.profile.phone,
            owner=cls.profile.owner,
            guest_profile=cls.profile,
            status="pending",
            source="website",
            request_key=uuid.uuid4(),
            request_hash="private-request-fingerprint",
            snapshot={"total": 36000},
        )
        cls.review = Review.objects.create(
            resort=cls.resort, booking=cls.booking, rating=4, text="Демонстрационный отзыв"
        )
        cls.audit = Audit.objects.create(
            actor="Проверка",
            resort=cls.resort,
            entity="bookings",
            entity_id=cls.booking.pk,
            action="create",
            label="Демо заявка",
            after={"text": "<script>alert('x')</script>"},
        )
        cls.payment = DemoPayment.objects.create(
            booking=cls.booking,
            request_key=uuid.uuid4(),
            outcome="success",
            status="refunded",
            amount=36000,
            refunded_amount=36000,
            receipt={"source": "demo"},
        )
        cls.refund = DemoRefund.objects.create(
            payment=cls.payment, amount=36000, percent=100, actor_kind="guest"
        )

    def setUp(self):
        self.client.force_login(self.operator)

    def change_url(self, obj):
        opts = obj._meta
        return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])

    def test_index_shows_database_metrics_and_correct_workspace_link(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Тыныс · управление платформой")
        self.assertContains(response, "https://staff.example.test/staff")
        cards = response.context["operation_cards"]
        self.assertEqual([card["count"] for card in cards], [1, 1, 0, 1, 1])
        for card in cards:
            with self.subTest(card=card["label"]):
                self.assertEqual(self.client.get(card["url"]).status_code, 200)

    def test_all_operations_models_have_read_only_searchable_views(self):
        records = [
            self.operator,
            self.resort,
            self.room,
            self.tariff,
            self.profile,
            self.guest,
            self.booking,
            self.review,
            self.audit,
            self.payment,
            self.refund,
            self.asset,
        ]
        for obj in records:
            with self.subTest(model=obj._meta.label):
                model_admin = platform_admin_site._registry[type(obj)]
                self.assertTrue(model_admin.search_fields)
                opts = obj._meta
                response = self.client.get(
                    reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
                )
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context["action_form"])
                self.assertEqual(self.client.get(self.change_url(obj)).status_code, 200)
                self.assertEqual(
                    self.client.post(self.change_url(obj), {"status": "cancelled"}).status_code, 403
                )
                self.assertEqual(
                    self.client.get(
                        reverse(f"admin:{opts.app_label}_{opts.model_name}_add")
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.post(
                        reverse(f"admin:{opts.app_label}_{opts.model_name}_delete", args=[obj.pk]),
                        {"post": "yes"},
                    ).status_code,
                    403,
                )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")
        self.assertEqual(DemoRefund.objects.get(pk=self.refund.pk).amount, 36000)

    def test_manager_and_platform_role_without_superuser_cannot_enter_console(self):
        for user in [self.manager, self.operator]:
            user.is_superuser = False
            user.save(update_fields=["is_superuser"])
            self.client.force_login(user)
            for url in [
                reverse("admin:index"),
                self.change_url(self.booking),
                reverse("admin:booking_guestaccount_changelist"),
            ]:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("admin:login"), response.url)

    def test_admin_login_rejects_staff_manager_even_with_valid_password(self):
        self.client.logout()
        response = self.client.post(
            reverse("admin:login"),
            {"username": self.manager.email, "password": PASSWORD, "next": reverse("admin:index")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_guest_and_staff_hashes_and_ownership_keys_are_not_rendered(self):
        for obj, secrets in [
            (self.guest, [self.guest.password, self.profile.owner]),
            (self.profile, [self.profile.owner]),
            (self.operator, [self.operator.password]),
            (self.booking, [self.profile.owner, self.booking.request_hash]),
            (self.asset, [self.asset.storage_key, self.profile.owner]),
        ]:
            response = self.client.get(self.change_url(obj))
            self.assertEqual(response.status_code, 200)
            for secret in secrets:
                self.assertNotContains(response, secret)
        self.assertNotIn(GuestChallenge, platform_admin_site._registry)
        self.assertNotIn(LoginAttempt, platform_admin_site._registry)

    def test_search_filters_and_structured_data_escape_untrusted_content(self):
        url = reverse("admin:booking_booking_changelist")
        self.assertEqual(self.client.get(url, {"q": "Демо гость"}).context["cl"].result_count, 1)
        self.assertEqual(
            self.client.get(url, {"q": "Отсутствующий гость"}).context["cl"].result_count, 0
        )
        self.assertEqual(
            self.client.get(url, {"status__exact": "confirmed"}).context["cl"].result_count, 0
        )
        response = self.client.get(self.change_url(self.audit))
        self.assertNotContains(response, "<script>alert('x')</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_admin_login_requires_csrf(self):
        response = Client(enforce_csrf_checks=True).post(
            reverse("admin:login"), {"username": self.operator.email, "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_login_is_limited_by_database_counter(self):
        self.client.logout()
        key = hashlib.sha256(f"admin-email:{self.operator.email}".encode()).hexdigest()
        LoginAttempt.objects.create(key=key, count=30, since=timezone.now())
        response = self.client.post(
            reverse("admin:login"),
            {"username": self.operator.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].non_field_errors().as_data()[0].code, "rate_limited"
        )
        self.assertNotIn("_auth_user_id", self.client.session)
