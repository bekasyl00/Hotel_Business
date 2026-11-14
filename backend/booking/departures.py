"""Idempotent departure processing for the hosted scheduler."""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import DateField, DateTimeField, ExpressionWrapper, F, Func
from django.utils import timezone

from commerce.services import has_paid_booking

from .models import Booking, Resort
from .stays import complete_checkout


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
        Booking.objects.filter(
            status="confirmed", checked_in_at__isnull=False, checked_out_at__isnull=True
        )
        .annotate(
            departure_date=Func(F("stay"), function="upper", output_field=DateField()),
            departure_local=ExpressionWrapper(
                F("departure_date") + F("resort__check_in_time"), output_field=DateTimeField()
            ),
            departure_at=Func(
                F("resort__time_zone"), F("departure_local"),
                function="timezone", output_field=DateTimeField(),
            ),
        )
        .filter(departure_at__lte=now)
        .select_related("resort__account")
        .order_by("departure_at", "id")[:limit]
    )
    completed = 0
    for candidate in candidates:
        with transaction.atomic():
            resort = Resort.objects.select_for_update().get(pk=candidate.resort_id)
            booking = Booking.objects.select_for_update().get(pk=candidate.pk)
            if (
                booking.status != "confirmed"
                or not booking.checked_in_at
                or booking.checked_out_at
                or not has_paid_booking(booking)
            ):
                continue
            zone = ZoneInfo(resort.time_zone)
            checkout_at = datetime.combine(
                booking.stay.upper, resort.check_in_time, tzinfo=zone
            ).astimezone(timezone.get_current_timezone())
            if now < checkout_at:
                continue
            complete_checkout(booking, resort.account, now)
            completed += 1
    return completed
