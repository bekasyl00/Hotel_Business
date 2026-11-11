import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
from django.db import migrations, models


def validate_place_allocations(apps, schema_editor):
    Room = apps.get_model("booking", "Room")
    RoomPlace = apps.get_model("booking", "RoomPlace")
    Booking = apps.get_model("booking", "Booking")
    BookingAllocation = apps.get_model("booking", "BookingAllocation")

    for room in Room.objects.all():
        active_count = RoomPlace.objects.filter(room_id=room.pk, status="active").count()
        if active_count != room.capacity:
            raise RuntimeError(
                f"Room {room.pk} capacity ({room.capacity}) does not match active places ({active_count})."
            )

    missing = Booking.objects.filter(allocations__isnull=True).count()
    if missing:
        raise RuntimeError(f"Found {missing} bookings without BookingAllocation rows.")

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.id, b.id, a.place_id
            FROM booking_bookingallocation a
            JOIN booking_bookingallocation b
              ON a.place_id = b.place_id
             AND a.id < b.id
             AND a.stay && b.stay
            WHERE a.status IN ('pending', 'confirmed')
              AND b.status IN ('pending', 'confirmed')
            LIMIT 1
            """
        )
        conflict = cursor.fetchone()
        if conflict:
            raise RuntimeError(
                f"Conflicting active place allocations detected before constraint creation: {conflict}"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("booking", "0019_backfill_room_places_and_allocations"),
    ]

    operations = [
        migrations.RunPython(
            validate_place_allocations,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="bookingallocation",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                condition=models.Q(("status__in", ["pending", "confirmed"])),
                expressions=[
                    ("place", django.contrib.postgres.fields.ranges.RangeOperators.EQUAL),
                    ("stay", django.contrib.postgres.fields.ranges.RangeOperators.OVERLAPS),
                ],
                name="no_overlapping_active_place_allocations",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="booking",
            name="no_overlapping_active_bookings",
        ),
    ]
