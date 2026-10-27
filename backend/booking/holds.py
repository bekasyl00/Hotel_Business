from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Audit, Booking, Resort


def active_inventory(now=None):
    return Q(status="confirmed") | (
        Q(status="pending")
        & (Q(hold_expires_at__isnull=True) | Q(hold_expires_at__gt=now or timezone.now()))
    )


def expire_locked_holds(resort_id, now=None):
    """Caller holds the resort row lock in the same transaction as the inventory write."""
    expired = Booking.objects.filter(
        resort_id=resort_id, status="pending", hold_expires_at__lte=now or timezone.now()
    ).order_by("id")
    count = 0
    for booking in expired:
        booking.status = "expired"
        booking.version += 1
        booking.save(update_fields=["status", "version"])
        Audit.objects.create(
            actor="Система",
            resort_id=resort_id,
            entity="bookings",
            entity_id=booking.pk,
            action="payment_expired",
            label=booking.snapshot.get("roomName", "booking"),
            before={"status": "pending"},
            after={"status": "expired"},
        )
        count += 1
    return count


@transaction.atomic
def expire_resort_holds(resort_id):
    Resort.objects.select_for_update().get(pk=resort_id)
    return expire_locked_holds(resort_id)
