from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.db.models import Avg, BigIntegerField, Count, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Cast, Coalesce, TruncDay, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework import serializers

from commerce.models import DemoPayment, DemoRefund

from .errors import Problem
from .models import Booking, Resort, Review, Room
from .services import admin, require_staff

ZONE = ZoneInfo("Asia/Almaty")
STATUSES = ("pending", "confirmed", "rejected", "cancelled")
LIMIT = 500


def empty_metrics(*, statuses=True):
    data = {
        "bookingCount": 0,
        "bookedAmount": 0,
        "grossReceived": 0,
        "refunds": 0,
        "netReceived": 0,
        "reviewCount": 0,
        "averageRating": None,
    }
    if statuses:
        data["statuses"] = dict.fromkeys(STATUSES, 0)
    return data


def bounds(start, end):
    return (
        datetime.combine(start, time.min, tzinfo=ZONE),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=ZONE),
    )


def parse_period(params):
    today = timezone.now().astimezone(ZONE).date()
    end = serializers.DateField().run_validation(params.get("end", today.isoformat()))
    if end.year in (1, 9999):
        raise Problem("Этот календарный диапазон не поддерживается.")
    start = serializers.DateField().run_validation(
        params.get("start", (end - timedelta(days=27)).isoformat())
    )
    if start.year in (1, 9999):
        raise Problem("Этот календарный диапазон не поддерживается.")
    if end < start or (end - start).days >= 366:
        raise Problem("Выберите период от 1 до 366 дней включительно.")
    granularity = serializers.ChoiceField(choices=["day", "week", "month"]).run_validation(
        params.get("granularity", "day")
    )
    return start, end, granularity


def facts(resorts, start, end):
    lower, upper = bounds(start, end)
    window = {"created_at__gte": lower, "created_at__lt": upper}
    return {
        "bookings": Booking.objects.filter(resort__in=resorts, **window),
        "payments": DemoPayment.objects.filter(
            booking__resort__in=resorts, outcome="success", **window
        ),
        "refunds": DemoRefund.objects.filter(payment__booking__resort__in=resorts, **window),
        "reviews": Review.objects.filter(resort__in=resorts, **window),
    }


def aggregates(kind):
    if kind == "bookings":
        return {
            "bookingCount": Count("pk"),
            "bookedAmount": Sum(Cast("snapshot__total", BigIntegerField()), default=0),
            **{f"status_{status}": Count("pk", filter=Q(status=status)) for status in STATUSES},
        }
    if kind == "payments":
        return {"grossReceived": Sum("amount", default=0)}
    if kind == "refunds":
        return {"refunds": Sum("amount", default=0)}
    return {
        "reviewCount": Count("pk"),
        "averageRating": Avg("rating", filter=Q(status="approved")),
    }


def merge_metrics(target, values):
    for key, value in values.items():
        if key.startswith("status_"):
            if "statuses" in target:
                target["statuses"][key.removeprefix("status_")] = value
        elif key == "averageRating":
            target[key] = (
                float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                if value is not None
                else None
            )
        elif key in target:
            target[key] = value
    target["netReceived"] = target["grossReceived"] - target["refunds"]


def totals(source):
    result = empty_metrics()
    for kind, queryset in source.items():
        merge_metrics(result, queryset.aggregate(**aggregates(kind)))
    return result


def bucket_start(day, granularity):
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    if granularity == "month":
        return day.replace(day=1)
    return day


def series(source, start, end, granularity):
    rows = {}
    cursor = bucket_start(start, granularity)
    while cursor <= end:
        rows[cursor.isoformat()] = {"date": cursor.isoformat(), **empty_metrics(statuses=False)}
        if granularity == "month":
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            cursor += timedelta(days=7 if granularity == "week" else 1)
    truncate = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}[granularity]
    for kind, queryset in source.items():
        grouped = (
            queryset.annotate(bucket=truncate("created_at", tzinfo=ZONE))
            .values("bucket")
            .annotate(**aggregates(kind))
            .order_by()
        )
        for row in grouped:
            key = row.pop("bucket").date().isoformat()
            merge_metrics(rows[key], row)
    return list(rows.values())


def group_field(kind, dimension):
    field = "resort_id" if dimension == "resort" else "room_id"
    if kind == "bookings" or (kind == "reviews" and dimension == "resort"):
        return field
    if kind == "refunds":
        return f"payment__booking__{field}"
    return f"booking__{field}"


def financial_subquery(queryset, field):
    grouped = (
        queryset.filter(**{field: OuterRef("pk")})
        .order_by()
        .values(field)
        .annotate(value=Sum("amount"))
        .values("value")[:1]
    )
    return Coalesce(
        Subquery(grouped, output_field=BigIntegerField()), Value(0), output_field=BigIntegerField()
    )


def breakdown(source, resorts, dimension):
    catalog = (
        Resort.objects.filter(pk__in=resorts)
        if dimension == "resort"
        else Room.objects.filter(resort__in=resorts)
    )
    ranked = catalog.annotate(
        metric_gross=financial_subquery(source["payments"], group_field("payments", dimension)),
        metric_refunds=financial_subquery(source["refunds"], group_field("refunds", dimension)),
    ).annotate(metric_net=F("metric_gross") - F("metric_refunds"))
    fields = ["id", "name"] if dimension == "resort" else ["id", "resort_id", "title", "number"]
    records = list(ranked.order_by("-metric_net", "id").values(*fields)[: LIMIT + 1])
    truncated = len(records) > LIMIT
    result = {}
    for item in records[:LIMIT]:
        metadata = (
            {"resortId": item["id"], "name": item["name"]}
            if dimension == "resort"
            else {
                "roomId": item["id"],
                "resortId": item["resort_id"],
                "name": item["title"],
                "number": item["number"],
            }
        )
        result[item["id"]] = {**metadata, **empty_metrics()}
    if result:
        for kind, queryset in source.items():
            field = group_field(kind, dimension)
            for row in (
                queryset.filter(**{field + "__in": result})
                .values(field)
                .annotate(**aggregates(kind))
                .order_by()
            ):
                key = row.pop(field)
                merge_metrics(result[key], row)
    return list(result.values()), truncated


def analytics_for_request(request):
    require_staff(request.user)
    start, end, granularity = parse_period(request.query_params)
    resorts = (
        Resort.objects.all()
        if admin(request.user)
        else Resort.objects.filter(pk=request.user.resort_id)
    )
    selected = request.query_params.get("resortId")
    options = list(resorts.order_by("name", "id").values("id", "name"))
    if selected:
        require_staff(request.user, selected)
        if not resorts.filter(pk=selected).exists():
            raise Problem("Санаторий не найден.", 404)
        resorts = resorts.filter(pk=selected)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - (end - start)
    source = facts(resorts, start, end)
    by_resort, resorts_truncated = breakdown(source, resorts, "resort")
    by_room, rooms_truncated = breakdown(source, resorts, "room")
    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "granularity": granularity,
            "timeZone": str(ZONE),
        },
        "previousPeriod": {"start": previous_start.isoformat(), "end": previous_end.isoformat()},
        "paymentMode": "demo",
        "totals": totals(source),
        "previousTotals": totals(facts(resorts, previous_start, previous_end)),
        "series": series(source, start, end, granularity),
        "byResort": by_resort,
        "byRoom": by_room,
        "resorts": options,
        "truncated": {"byResort": resorts_truncated, "byRoom": rooms_truncated},
    }
