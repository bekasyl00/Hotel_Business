"""Idempotent departure processing for the hosted scheduler."""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .models import Booking, Resort


def complete_due_departures(now=None, *, limit=100):
    """Close paid confirmed stays whose scheduled checkout time has passed.

    The stay end is exclusive.  Resorts currently expose one operational time
    (check-in); using it for the next-day checkout keeps the rule deterministic
    until a separate checkout-time setting is introduced.  The operation is
    safe to run repeatedly from cron and prepares documents without exposing
    any guest identity data in the scheduler response.
    """
    now = now or timezone.now()
    candidates = list(
        Booking.objects.filter(status="confirmed", checked_out_at__isnull=True)
        .select_related("resort__account")
        .order_by("stay", "id")[:limit]
    )
    completed = 0
    for candidate in candidates:
        with transaction.atomic():
            resort = Resort.objects.select_for_update().get(pk=candidate.resort_id)
            booking = Booking.objects.select_for_update().get(pk=candidate.pk)
            if booking.status != "confirmed" or booking.checked_out_at:
                continue
            zone = ZoneInfo(resort.time_zone)
            checkout_at = datetime.combine(
                booking.stay.upper, resort.check_in_time, tzinfo=zone
            ).astimezone(timezone.get_current_timezone())
            if now < checkout_at:
                continue
            # A paid booking may have been admitted without a separate manual
            # check-in record in the early rollout.  Preserve the database
            # invariant by recording the scheduled arrival before departure.
            if not booking.checked_in_at:
                booking.checked_in_at = datetime.combine(
                    booking.stay.lower, resort.check_in_time, tzinfo=zone
                ).astimezone(timezone.get_current_timezone())
            booking.checked_out_at = now
            booking.version += 1
            booking.save(update_fields=["checked_in_at", "checked_out_at", "version"])
            from commerce.accounting.services import prepare_after_stay

            prepare_after_stay(booking, resort.account)
            completed += 1
    return completed
