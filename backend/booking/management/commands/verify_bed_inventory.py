import json
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from booking.models import Booking, BookingAllocation, Room, RoomPlace, place_label, place_pk_for


class Command(BaseCommand):
    help = "Validate RoomPlace and BookingAllocation invariants; dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply-backfill",
            action="store_true",
            help="Create missing RoomPlace and BookingAllocation records if any are missing.",
        )

    def handle(self, *args, **options):
        apply_backfill = bool(options.get("apply_backfill"))
        report = {
            "mode": "apply" if apply_backfill else "dry_run",
            "roomsTotal": 0,
            "placesTotal": 0,
            "roomsMissingPlaces": [],
            "roomsCapacityMismatch": [],
            "bookingsTotal": 0,
            "bookingsMissingAllocations": [],
            "bookingsStatusMismatch": [],
            "activeAllocationConflicts": [],
            "backfilledPlaces": 0,
            "backfilledAllocations": 0,
        }

        with transaction.atomic():
            for room in Room.objects.all().order_by("id"):
                report["roomsTotal"] += 1
                places = list(RoomPlace.objects.filter(room=room).order_by("position", "id"))
                report["placesTotal"] += len(places)
                active_count = sum(1 for p in places if p.status == "active")
                if not places:
                    report["roomsMissingPlaces"].append(room.pk)
                    if apply_backfill:
                        for pos in range(1, int(room.capacity or 1) + 1):
                            RoomPlace.objects.create(
                                id=place_pk_for(room.pk, pos),
                                room=room,
                                position=pos,
                                label=place_label(pos),
                                status="active",
                            )
                            report["backfilledPlaces"] += 1
                        active_count = int(room.capacity or 1)
                if active_count != room.capacity:
                    report["roomsCapacityMismatch"].append(
                        {"roomId": room.pk, "capacity": room.capacity, "activePlaces": active_count}
                    )

            for booking in Booking.objects.select_related("room").all().order_by("created_at", "id"):
                report["bookingsTotal"] += 1
                allocations = list(BookingAllocation.objects.filter(booking=booking))
                if not allocations:
                    report["bookingsMissingAllocations"].append(booking.pk)
                    if apply_backfill:
                        places = list(
                            RoomPlace.objects.filter(room=booking.room).order_by("position", "id")
                        )
                        target = (
                            places
                            if booking.status in ("pending", "confirmed")
                            else places[: max(1, min(int(booking.guests or 1), len(places)))]
                        )
                        for place in target:
                            BookingAllocation.objects.create(
                                booking=booking,
                                room=booking.room,
                                place=place,
                                stay=booking.stay,
                                status=booking.status,
                            )
                            report["backfilledAllocations"] += 1
                else:
                    if any(a.status != booking.status or a.stay != booking.stay for a in allocations):
                        report["bookingsStatusMismatch"].append(booking.pk)
                        if apply_backfill:
                            BookingAllocation.objects.filter(booking=booking).update(
                                status=booking.status, stay=booking.stay, room=booking.room
                            )

            with connection.cursor() as cursor:
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
                    LIMIT 20
                    """
                )
                for first_id, second_id, place_id in cursor.fetchall():
                    report["activeAllocationConflicts"].append(
                        {"firstAllocationId": first_id, "secondAllocationId": second_id, "placeId": place_id}
                    )

        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        if (
            report["roomsCapacityMismatch"]
            or report["activeAllocationConflicts"]
            or (
                not apply_backfill
                and (
                    report["roomsMissingPlaces"]
                    or report["bookingsMissingAllocations"]
                    or report["bookingsStatusMismatch"]
                )
            )
        ):
            raise CommandError("Bed inventory validation failed.")
