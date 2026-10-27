from decimal import ROUND_HALF_UP, Decimal


def freeze_commission(resort, total):
    """Commercial estimate, not a payout or accounting ledger entry."""
    percent = resort.commission_percent
    amount = (
        int((Decimal(total) * percent / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if percent is not None
        else None
    )
    return {
        "percent": str(percent) if percent is not None else None,
        "amount": amount,
        "resortAmount": total - amount if amount is not None else None,
        "currency": "KZT",
        "basis": "booking_total",
        "mode": "estimate",
        "refundHandling": "requires_reconciliation",
    }
