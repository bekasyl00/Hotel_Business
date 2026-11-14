"""Stay transitions shared by staff workflows and scheduled departures."""

from commerce.services import has_paid_booking

from .audit import log_change
from .errors import Problem
from .serializers import booking_data


def complete_checkout(booking, actor, now):
    """Record checkout while the caller holds the resort transaction lock."""
    if booking.status != "confirmed" or not has_paid_booking(booking):
        raise Problem("Сначала требуется подтверждённая сервером оплата.", 409)
    if not booking.checked_in_at or booking.checked_out_at:
        raise Problem("Для выезда гость должен быть заселён и ещё не выехать.", 409)
    before = booking_data(booking)
    booking.checked_out_at = now
    booking.version += 1
    booking.save(update_fields=["checked_out_at", "version"])
    log_change(actor, "bookings", booking, "check-out", before, booking_data(booking), booking.resort_id)
    from commerce.accounting.services import prepare_after_stay

    prepare_after_stay(booking, actor)
    return booking
