import uuid
from datetime import time

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.models import Q


def new_id():
    return str(uuid.uuid4())


class Record(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=new_id, editable=False)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class Resort(Record):
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    feature = models.CharField(max_length=100, blank=True)
    lat = models.FloatField()
    lng = models.FloatField()
    rating = models.FloatField(default=0)
    category = models.CharField(
        max_length=16,
        default="wellness",
        choices=[(v, v) for v in ["wellness", "family", "premium", "nature"]],
    )
    resort_class = models.CharField(
        max_length=16,
        default="standard",
        choices=[(v, v) for v in ["standard", "comfort", "premium"]],
    )
    check_in_time = models.TimeField(default=time(14, 0))
    time_zone = models.CharField(max_length=64, default="Asia/Almaty")
    amenities = models.JSONField(default=list)
    media = models.JSONField(default=list)
    status = models.CharField(
        max_length=16, default="draft", choices=[(v, v) for v in ["draft", "published", "archived"]]
    )


class User(AbstractUser):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=100)
    role = models.CharField(
        max_length=16, default="manager", choices=[("admin", "admin"), ("manager", "manager")]
    )
    resort = models.ForeignKey(Resort, null=True, blank=True, on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]


class Room(Record):
    resort = models.ForeignKey(Resort, on_delete=models.PROTECT, related_name="rooms")
    number = models.CharField(max_length=30)
    category = models.CharField(
        max_length=16, choices=[(v, v) for v in ["standard", "comfort", "suite"]]
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    amenities = models.JSONField(default=list)
    media = models.JSONField(default=list)
    area = models.PositiveIntegerField()
    capacity = models.PositiveSmallIntegerField()
    beds = models.CharField(max_length=100)
    price = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        default="active",
        choices=[("active", "active"), ("maintenance", "maintenance")],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["resort", "number"], name="unique_room_number"),
            models.CheckConstraint(
                condition=Q(capacity__gte=1, capacity__lte=4), name="room_capacity"
            ),
        ]


class Tariff(Record):
    resort = models.ForeignKey(Resort, on_delete=models.PROTECT, related_name="tariffs")
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True)
    supplement = models.PositiveIntegerField(default=0)
    features = models.JSONField(default=list)
    price_kind = models.CharField(
        max_length=16, default="regular", choices=[("regular", "regular"), ("discount", "discount")]
    )
    discount_percent = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=16, default="active", choices=[("active", "active"), ("disabled", "disabled")]
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_percent__lte=90)
                & (Q(price_kind="discount") | Q(price_kind="regular", discount_percent=0)),
                name="valid_tariff_discount",
            )
        ]


class GuestProfile(Record):
    owner = models.CharField(max_length=64, unique=True, editable=False)
    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    avatar = models.ForeignKey(
        "MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="avatar_profiles",
    )


class GuestAccount(Record):
    phone = models.CharField(max_length=16, unique=True)
    password = models.CharField(max_length=128)
    profile = models.OneToOneField(GuestProfile, on_delete=models.PROTECT, related_name="account")
    auth_version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GuestChallenge(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=new_id, editable=False)
    phone = models.CharField(max_length=16)
    purpose = models.CharField(
        max_length=16, choices=[("register", "register"), ("reset", "reset")]
    )
    scope_hash = models.CharField(max_length=64)
    owner = models.CharField(max_length=64)
    code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["phone", "purpose", "-created_at"])]


class Booking(Record):
    resort = models.ForeignKey(Resort, on_delete=models.PROTECT)
    room = models.ForeignKey(Room, on_delete=models.PROTECT)
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT)
    stay = DateRangeField()
    guests = models.PositiveSmallIntegerField()
    guest_label = models.CharField(max_length=80)
    guest_phone = models.CharField(max_length=30, blank=True)
    owner = models.CharField(max_length=64, db_index=True)
    guest_profile = models.ForeignKey(
        GuestProfile, null=True, blank=True, on_delete=models.PROTECT, related_name="bookings"
    )
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        default="pending",
        choices=[(v, v) for v in ["pending", "confirmed", "rejected", "cancelled"]],
    )
    source = models.CharField(max_length=16, choices=[("website", "website"), ("staff", "staff")])
    created_at = models.DateTimeField(auto_now_add=True)
    snapshot = models.JSONField(default=dict)
    request_key = models.UUIDField(unique=True)
    request_hash = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(checked_out_at__isnull=True)
                | Q(checked_in_at__isnull=False, checked_out_at__gte=models.F("checked_in_at")),
                name="checkout_after_checkin",
            ),
            ExclusionConstraint(
                name="no_overlapping_active_bookings",
                expressions=[("room", RangeOperators.EQUAL), ("stay", RangeOperators.OVERLAPS)],
                condition=Q(status__in=["pending", "confirmed"]),
            ),
        ]
        indexes = [models.Index(fields=["resort", "status", "-created_at"])]


class Audit(Record):
    at = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=100)
    resort = models.ForeignKey(Resort, null=True, on_delete=models.PROTECT)
    entity = models.CharField(max_length=30)
    entity_id = models.CharField(max_length=64)
    action = models.CharField(max_length=30)
    label = models.CharField(max_length=200)
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)


class Review(Record):
    resort = models.ForeignKey(Resort, on_delete=models.PROTECT, related_name="reviews")
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="review")
    rating = models.PositiveSmallIntegerField()
    text = models.TextField()
    photos = models.JSONField(default=list)
    status = models.CharField(
        max_length=16,
        default="pending",
        choices=[(v, v) for v in ["pending", "approved", "rejected"]],
    )
    reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5), name="review_rating_range"
            )
        ]
        indexes = [models.Index(fields=["resort", "status", "-created_at"])]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    since = models.DateTimeField()


class MediaAsset(Record):
    purpose = models.CharField(
        max_length=16, choices=[(v, v) for v in ["catalog", "review", "avatar"]]
    )
    kind = models.CharField(max_length=8, choices=[("image", "image"), ("video", "video")])
    storage_key = models.CharField(max_length=300, unique=True, editable=False)
    size = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=40)
    resort = models.ForeignKey(Resort, null=True, blank=True, on_delete=models.PROTECT)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.PROTECT)
    profile = models.ForeignKey(GuestProfile, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def url(self):
        return f"/api/media/files/{self.pk}"

    class Meta:
        indexes = [models.Index(fields=["purpose", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        purpose="catalog",
                        resort__isnull=False,
                        booking__isnull=True,
                        profile__isnull=True,
                    )
                    | Q(
                        purpose="review",
                        resort__isnull=False,
                        booking__isnull=False,
                        profile__isnull=True,
                        kind="image",
                    )
                    | Q(
                        purpose="avatar",
                        resort__isnull=True,
                        booking__isnull=True,
                        profile__isnull=False,
                        kind="image",
                    )
                ),
                name="media_owner_matches_purpose",
            )
        ]
