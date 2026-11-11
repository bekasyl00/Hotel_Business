import uuid
from datetime import time

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.models import Q
from django.utils.crypto import salted_hmac


def new_id():
    return str(uuid.uuid4())


def place_label(position: int) -> str:
    n = int(position)
    if n < 1:
        raise ValueError("position must be >= 1")
    chars = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("a") + rem))
    return "".join(reversed(chars))


def place_pk_for(room_pk: str, position: int) -> str:
    candidate = f"{room_pk}-p{position}"
    return candidate if len(candidate) <= 64 else new_id()


class Record(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=new_id, editable=False)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class Resort(Record):
    account = models.ForeignKey("User", on_delete=models.PROTECT, related_name="managed_resorts")
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    description_after = models.TextField(blank=True)
    staff_whatsapp = models.CharField(max_length=16, blank=True)
    two_gis_url = models.URLField(max_length=1000, blank=True)
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
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    amenities = models.JSONField(default=list)
    media = models.JSONField(default=list)
    status = models.CharField(
        max_length=16, default="draft", choices=[(v, v) for v in ["draft", "published", "archived"]]
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(commission_percent__isnull=True)
                | Q(commission_percent__gte=0, commission_percent__lte=100),
                name="resort_commission_percent_range",
            )
        ]


class User(AbstractUser):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=100)
    job_title = models.CharField(max_length=100, blank=True)
    contact_phone = models.CharField(max_length=16, blank=True)
    profile_version = models.PositiveIntegerField(default=1)
    role = models.CharField(
        max_length=16,
        default="manager",
        choices=[("admin", "admin"), ("manager", "manager"), ("accountant", "accountant")],
    )
    resort = models.ForeignKey(Resort, null=True, blank=True, on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def _get_session_auth_hash(self, secret=None):
        # Versioned staff changes invalidate browser cookies as well as native credentials.
        return salted_hmac(
            "booking.User.get_session_auth_hash",
            f"{self.password}:{self.version}:{self.email}:{self.role}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()


class Room(Record):
    resort = models.ForeignKey(Resort, on_delete=models.PROTECT, related_name="rooms")
    number = models.CharField(max_length=30)
    category = models.CharField(
        max_length=16, choices=[(v, v) for v in ["standard", "comfort", "suite"]]
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    description_after = models.TextField(blank=True)
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

    def ensure_places(self):
        existing = list(self.places.all().order_by("position", "id"))
        if existing:
            return existing
        created = []
        for pos in range(1, int(self.capacity or 1) + 1):
            created.append(
                RoomPlace.objects.create(
                    id=place_pk_for(self.pk, pos),
                    room=self,
                    position=pos,
                    label=place_label(pos),
                    status="active",
                )
            )
        return created

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not getattr(self, "_managed_places", False):
            self.ensure_places()


class RoomPlace(Record):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="places")
    position = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=16)
    status = models.CharField(
        max_length=16,
        default="active",
        choices=[("active", "active"), ("maintenance", "maintenance")],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def unit_label(self):
        return f"{self.room.number}{self.label}"

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["room", "position"], name="unique_room_place_position"),
            models.UniqueConstraint(fields=["room", "label"], name="unique_room_place_label"),
            models.CheckConstraint(
                condition=Q(position__gte=1, position__lte=12), name="room_place_position_range"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "maintenance"]), name="room_place_status_valid"
            ),
        ]


class RoomPricePeriod(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="price_periods")
    label = models.CharField(max_length=80)
    stay = DateRangeField()
    price = models.PositiveIntegerField()

    class Meta:
        ordering = ["stay"]
        constraints = [
            ExclusionConstraint(
                name="no_overlapping_room_prices",
                expressions=[("room", RangeOperators.EQUAL), ("stay", RangeOperators.OVERLAPS)],
            ),
            models.CheckConstraint(
                condition=Q(price__lte=10000000), name="room_period_price_limit"
            ),
            models.CheckConstraint(condition=Q(stay__isempty=False), name="room_period_not_empty"),
        ]


class Tariff(Record):
    resort = models.ForeignKey(Resort, on_delete=models.PROTECT, related_name="tariffs")
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True)
    supplement = models.PositiveIntegerField(default=0)
    children_under_two_free = models.BooleanField(
        default=False, db_column="children_under_three_free"
    )
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
    phone_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
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
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT, null=True, blank=True)
    stay = DateRangeField()
    guests = models.PositiveSmallIntegerField()
    guest_label = models.CharField(max_length=80)
    guest_phone = models.CharField(max_length=30, blank=True)
    staff_notes = models.TextField(blank=True, default="", max_length=2000)
    owner = models.CharField(max_length=64, db_index=True)
    guest_profile = models.ForeignKey(
        GuestProfile, null=True, blank=True, on_delete=models.PROTECT, related_name="bookings"
    )
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        default="pending",
        choices=[(v, v) for v in ["pending", "confirmed", "rejected", "cancelled", "expired"]],
    )
    hold_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
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
        ]
        indexes = [
            models.Index(fields=["resort", "status", "-created_at"]),
            models.Index(
                fields=["hold_expires_at"],
                condition=Q(status="pending"),
                name="booking_pending_hold_idx",
            ),
        ]

    def _sync_default_allocations(self):
        places = list(self.room.ensure_places())
        existing = list(self.allocations.all().order_by("place__position", "place_id", "id"))
        if existing:
            BookingAllocation.objects.filter(booking=self).exclude(
                status=self.status, stay=self.stay, room=self.room
            ).update(status=self.status, stay=self.stay, room=self.room)
            return existing
        active_places = [p for p in places if p.status == "active"] or places
        needed = max(1, min(int(self.guests or 1), len(active_places) or 1))
        if self.status in ("pending", "confirmed") and active_places:
            busy_ids = set(
                BookingAllocation.objects.filter(
                    place__in=active_places,
                    status__in=["pending", "confirmed"],
                    stay__overlap=self.stay,
                )
                .exclude(booking=self)
                .values_list("place_id", flat=True)
            )
            free_places = [p for p in active_places if p.pk not in busy_ids]
            selected = free_places[:needed]
            if len(selected) < needed:
                used = {p.pk for p in selected}
                for p in active_places:
                    if p.pk not in used:
                        selected.append(p)
                        if len(selected) == needed:
                            break
        else:
            selected = active_places[:needed]
        created = []
        for place in selected:
            created.append(
                BookingAllocation.objects.create(
                    booking=self,
                    room=self.room,
                    place=place,
                    stay=self.stay,
                    status=self.status,
                )
            )
        return created

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not getattr(self, "_managed_allocations", False):
            self._sync_default_allocations()


class BookingAllocation(Record):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="allocations")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="allocations")
    place = models.ForeignKey(RoomPlace, on_delete=models.PROTECT, related_name="allocations")
    stay = DateRangeField()
    status = models.CharField(
        max_length=16,
        default="pending",
        choices=[(v, v) for v in ["pending", "confirmed", "rejected", "cancelled", "expired"]],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["place__position", "place_id", "id"]
        indexes = [
            models.Index(fields=["room", "status"], name="booking_alloc_room_status_idx"),
            models.Index(fields=["booking", "status"], name="booking_alloc_book_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "place"], name="unique_booking_place_allocation"
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=["pending", "confirmed", "rejected", "cancelled", "expired"]
                ),
                name="booking_allocation_status_valid",
            ),
            ExclusionConstraint(
                name="no_overlapping_active_place_allocations",
                expressions=[("place", RangeOperators.EQUAL), ("stay", RangeOperators.OVERLAPS)],
                condition=Q(status__in=["pending", "confirmed"]),
            ),
        ]


class StaffNotification(Record):
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="staff_notifications"
    )
    resort = models.ForeignKey(
        Resort, on_delete=models.CASCADE, related_name="staff_notifications"
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="staff_notifications"
    )
    kind = models.CharField(
        max_length=32,
        choices=[
            (v, v)
            for v in [
                "booking_created",
                "booking_paid",
                "booking_cancelled",
                "booking_expired",
            ]
        ],
    )
    dedup_key = models.CharField(max_length=160, unique=True)
    payload = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["recipient", "read_at", "-created_at"],
                name="staff_notif_recip_read_idx",
            ),
            models.Index(
                fields=["resort", "-created_at"],
                name="staff_notif_resort_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    kind__in=[
                        "booking_created",
                        "booking_paid",
                        "booking_cancelled",
                        "booking_expired",
                    ]
                ),
                name="staff_notification_kind_valid",
            )
        ]


class StaffPushDevice(Record):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_devices")
    platform = models.CharField(
        max_length=16, choices=[("ios", "ios"), ("android", "android")]
    )
    token_hash = models.CharField(max_length=64, unique=True)
    push_token = models.CharField(max_length=512)
    device_label = models.CharField(max_length=120, blank=True, default="")
    app_version = models.CharField(max_length=40, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["user", "is_active"], name="staff_push_user_active_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(platform__in=["ios", "android"]),
                name="staff_push_platform_valid",
            )
        ]


class StaffPushDelivery(Record):
    notification = models.ForeignKey(
        StaffNotification, on_delete=models.CASCADE, related_name="push_deliveries"
    )
    device = models.ForeignKey(
        StaffPushDevice, on_delete=models.CASCADE, related_name="deliveries"
    )
    dedup_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(
        max_length=24,
        default="pending",
        choices=[
            (v, v)
            for v in ["pending", "sent", "skipped_unconfigured", "failed"]
        ],
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=240, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=["pending", "sent", "skipped_unconfigured", "failed"]
                ),
                name="staff_push_delivery_status_valid",
            )
        ]


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

    class Meta:
        indexes = [models.Index(fields=["since"], name="booking_rate_since_idx")]


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
