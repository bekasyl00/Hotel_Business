import django.contrib.postgres.fields.ranges
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import booking.models


class Migration(migrations.Migration):
    dependencies = [
        ("booking", "0017_operations_hold_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoomPlace",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=booking.models.new_id,
                        editable=False,
                        max_length=64,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("position", models.PositiveSmallIntegerField()),
                ("label", models.CharField(max_length=16)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "active"), ("maintenance", "maintenance")],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="places",
                        to="booking.room",
                    ),
                ),
            ],
            options={
                "ordering": ["position", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("room", "position"), name="unique_room_place_position"
                    ),
                    models.UniqueConstraint(
                        fields=("room", "label"), name="unique_room_place_label"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("position__gte", 1), ("position__lte", 12)),
                        name="room_place_position_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("status__in", ["active", "maintenance"])),
                        name="room_place_status_valid",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="BookingAllocation",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=booking.models.new_id,
                        editable=False,
                        max_length=64,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("stay", django.contrib.postgres.fields.ranges.DateRangeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("confirmed", "confirmed"),
                            ("rejected", "rejected"),
                            ("cancelled", "cancelled"),
                            ("expired", "expired"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="allocations",
                        to="booking.booking",
                    ),
                ),
                (
                    "place",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="allocations",
                        to="booking.roomplace",
                    ),
                ),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="allocations",
                        to="booking.room",
                    ),
                ),
            ],
            options={
                "ordering": ["place__position", "place_id", "id"],
                "indexes": [
                    models.Index(
                        fields=["room", "status"], name="booking_alloc_room_status_idx"
                    ),
                    models.Index(
                        fields=["booking", "status"], name="booking_alloc_book_status_idx"
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("booking", "place"),
                        name="unique_booking_place_allocation",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "status__in",
                                ["pending", "confirmed", "rejected", "cancelled", "expired"],
                            )
                        ),
                        name="booking_allocation_status_valid",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="StaffNotification",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=booking.models.new_id,
                        editable=False,
                        max_length=64,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("booking_created", "booking_created"),
                            ("booking_paid", "booking_paid"),
                            ("booking_cancelled", "booking_cancelled"),
                            ("booking_expired", "booking_expired"),
                        ],
                        max_length=32,
                    ),
                ),
                ("dedup_key", models.CharField(max_length=160, unique=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_notifications",
                        to="booking.booking",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "resort",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_notifications",
                        to="booking.resort",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["recipient", "read_at", "-created_at"],
                        name="staff_notif_recip_read_idx",
                    ),
                    models.Index(
                        fields=["resort", "-created_at"],
                        name="staff_notif_resort_created_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "kind__in",
                                [
                                    "booking_created",
                                    "booking_paid",
                                    "booking_cancelled",
                                    "booking_expired",
                                ],
                            )
                        ),
                        name="staff_notification_kind_valid",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="StaffPushDevice",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=booking.models.new_id,
                        editable=False,
                        max_length=64,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "platform",
                    models.CharField(
                        choices=[("ios", "ios"), ("android", "android")], max_length=16
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("push_token", models.CharField(max_length=512)),
                ("device_label", models.CharField(blank=True, default="", max_length=120)),
                ("app_version", models.CharField(blank=True, default="", max_length=40)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_devices",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["user", "is_active"], name="staff_push_user_active_idx"
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("platform__in", ["ios", "android"])),
                        name="staff_push_platform_valid",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="StaffPushDelivery",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=booking.models.new_id,
                        editable=False,
                        max_length=64,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("dedup_key", models.CharField(max_length=160, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("sent", "sent"),
                            ("skipped_unconfigured", "skipped_unconfigured"),
                            ("failed", "failed"),
                        ],
                        default="pending",
                        max_length=24,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, default="", max_length=240)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="booking.staffpushdevice",
                    ),
                ),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_deliveries",
                        to="booking.staffnotification",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "status__in",
                                ["pending", "sent", "skipped_unconfigured", "failed"],
                            )
                        ),
                        name="staff_push_delivery_status_valid",
                    ),
                ],
            },
        ),
        migrations.RunSQL(
            """
            ALTER TABLE booking_roomplace ENABLE ROW LEVEL SECURITY;
            ALTER TABLE booking_bookingallocation ENABLE ROW LEVEL SECURITY;
            ALTER TABLE booking_staffnotification ENABLE ROW LEVEL SECURITY;
            ALTER TABLE booking_staffpushdevice ENABLE ROW LEVEL SECURITY;
            ALTER TABLE booking_staffpushdelivery ENABLE ROW LEVEL SECURITY;
            REVOKE ALL ON booking_roomplace FROM PUBLIC;
            REVOKE ALL ON booking_bookingallocation FROM PUBLIC;
            REVOKE ALL ON booking_staffnotification FROM PUBLIC;
            REVOKE ALL ON booking_staffpushdevice FROM PUBLIC;
            REVOKE ALL ON booking_staffpushdelivery FROM PUBLIC;
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON booking_roomplace FROM anon;
                    REVOKE ALL ON booking_bookingallocation FROM anon;
                    REVOKE ALL ON booking_staffnotification FROM anon;
                    REVOKE ALL ON booking_staffpushdevice FROM anon;
                    REVOKE ALL ON booking_staffpushdelivery FROM anon;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON booking_roomplace FROM authenticated;
                    REVOKE ALL ON booking_bookingallocation FROM authenticated;
                    REVOKE ALL ON booking_staffnotification FROM authenticated;
                    REVOKE ALL ON booking_staffpushdevice FROM authenticated;
                    REVOKE ALL ON booking_staffpushdelivery FROM authenticated;
                END IF;
            END $$;
            """,
            migrations.RunSQL.noop,
        ),
    ]
