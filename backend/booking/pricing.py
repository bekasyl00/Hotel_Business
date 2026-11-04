from datetime import timedelta


def quote_stay(room, tariff, start, end, guests, children_ages=None):
    """Called under the resort lock when committing a booking. End is exclusive."""
    periods = list(room.price_periods.all())
    discount = tariff.discount_percent if tariff and tariff.price_kind == "discount" else 0
    supplement = tariff.supplement if tariff else 0
    children_free = tariff.children_under_three_free if tariff else False
    children_ages = children_ages or []
    free_children = sum(age < 3 for age in children_ages) if children_free else 0
    chargeable_guests = guests - free_children
    lines = []
    for offset in range((end - start).days):
        day = start + timedelta(days=offset)
        period = next((p for p in periods if p.stay.lower <= day < p.stay.upper), None)
        room_price = period.price if period else room.price
        regular = room_price + supplement * chargeable_guests
        lines.append(
            {
                "date": day.isoformat(),
                "roomPrice": room_price,
                "periodLabel": period.label if period else "",
                "supplementTotal": supplement * chargeable_guests,
                "regularNightly": regular,
                "nightly": (regular * (100 - discount) + 50) // 100,
            }
        )
    prices = {line["nightly"] for line in lines}
    regular_prices = {line["regularNightly"] for line in lines}
    return {
        "pricingVersion": 2,
        "childrenAges": children_ages,
        "childrenUnderThreeFree": children_free,
        "freeChildren": free_children,
        "chargeableGuests": chargeable_guests,
        "nightlyBreakdown": lines,
        "regularNightly": next(iter(regular_prices)) if len(regular_prices) == 1 else None,
        "nightly": next(iter(prices)) if len(prices) == 1 else None,
        "priceKind": tariff.price_kind if tariff else "regular",
        "discountPercent": discount,
        "nights": len(lines),
        "total": sum(line["nightly"] for line in lines),
    }
