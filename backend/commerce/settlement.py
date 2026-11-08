"""Frozen platform fee and independently recorded payment at the property."""

from decimal import ROUND_HALF_UP, Decimal


def freeze_payment_terms(resort, total):
    from booking.errors import Problem

    value = resort.commission_percent
    if value is None or value <= 0:
        raise Problem(
            "Для санатория ещё не согласована комиссия онлайн-бронирования.",
            409,
            "booking_fee_not_configured",
        )
    proposed = Decimal(total) * value / Decimal(100)
    online = int(proposed.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if online < 1:
        raise Problem("Сумма комиссии должна быть не менее 1 ₸.", 409, "booking_fee_too_small")
    return {
        "version": 1,
        "total": total + online,
        "accommodationTotal": total,
        "mode": "percent",
        "value": str(value),
        "onlineAmount": online,
        "onsiteAmount": total,
    }


def payment_terms(booking):
    terms = booking.snapshot.get("paymentTerms")
    if terms is not None:
        return dict(terms)
    # Historical reservations retain their full online collection agreement.
    total = booking.snapshot.get("total", 0)
    return {
        "version": 0,
        "total": total,
        "accommodationTotal": total,
        "mode": "full",
        "value": "100",
        "onlineAmount": total,
        "onsiteAmount": 0,
    }


def online_amount(booking):
    return payment_terms(booking)["onlineAmount"]


def onsite_data(booking):
    record = getattr(booking, "onsite_settlement", None)
    return {
        "status": "recorded" if record else "due",
        "amount": record.amount if record else payment_terms(booking)["onsiteAmount"],
        "method": record.method if record else None,
        "recordedAt": record.created_at.isoformat() if record else None,
    }
