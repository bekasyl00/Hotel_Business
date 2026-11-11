import uuid
from django.db import migrations


def _place_label(position: int) -> str:
    n = int(position)
    chars = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("a") + rem))
    return "".join(reversed(chars))


def _place_pk(room_pk: str, position: int) -> str:
    candidate = f"{room_pk}-p{position}"
    return candidate if len(candidate) <= 64 else str(uuid.uuid4())


def backfill_places_and_allocations(apps, schema_editor):
    Room = apps.get_model("booking", "Room")
    RoomPlace = apps.get_model("booking", "RoomPlace")
    Booking = apps.get_model("booking", "Booking")
    BookingAllocation = apps.get_model("booking", "BookingAllocation")

    places_by_room = {}
    for room in Room.objects.all().order_by("id"):
        existing = list(RoomPlace.objects.filter(room_id=room.pk).order_by("position", "id"))
        existing_positions = {p.position for p in existing}
        for pos in range(1, int(room.capacity or 1) + 1):
            if pos not in existing_positions:
                place = RoomPlace.objects.create(
                    id=_place_pk(room.pk, pos),
                    room_id=room.pk,
                    position=pos,
                    label=_place_label(pos),
                    status="active",
                    version=1,
                )
                existing.append(place)
        existing.sort(key=lambda item: (item.position, item.pk))
        places_by_room[room.pk] = existing

    for booking in Booking.objects.all().order_by("created_at", "id"):
        if BookingAllocation.objects.filter(booking_id=booking.pk).exists():
            continue
        room_places = places_by_room.get(booking.room_id)
        if not room_places:
            room = Room.objects.get(pk=booking.room_id)
            room_places = [
                RoomPlace.objects.create(
                    id=_place_pk(room.pk, pos),
                    room_id=room.pk,
                    position=pos,
                    label=_place_label(pos),
                    status="active",
                    version=1,
                )
                for pos in range(1, int(room.capacity or 1) + 1)
            ]
            places_by_room[room.pk] = room_places
        if booking.status in ("pending", "confirmed"):
            # Legacy active bookings promised the whole physical room;
            # allocate all places of the room so no neighbor is sold into an existing reservation.
            target_places = room_places
        else:
            count = max(1, min(int(booking.guests or 1), len(room_places)))
            target_places = room_places[:count]
        for place in target_places:
            BookingAllocation.objects.create(
                id=str(uuid.uuid4()),
                booking_id=booking.pk,
                room_id=booking.room_id,
                place_id=place.pk,
                stay=booking.stay,
                status=booking.status,
                version=1,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("booking", "0018_room_places_and_allocations_expand"),
    ]

    operations = [
        migrations.RunPython(
            backfill_places_and_allocations,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
