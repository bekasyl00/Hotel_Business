"""Bounded public availability counts; no booking or guest details leave this module."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework import serializers

from .errors import Problem
from .holds import active_allocation_inventory
from .models import BookingAllocation, Resort, Room, RoomPricePeriod
from .pricing import room_night_price


def inclusive_price(amount, percent):
    """Whole-KZT one-night display; a booking still freezes its entire-stay fee."""
    if percent is None or percent <= 0:
        return amount
    rate_units = int(percent * 100)
    return amount + (amount * rate_units + 5000) // 10000


def available_price(day, available_ids, room_by_id, periods_by_room, guests, percent):
    candidates = [
        (room_night_price(room_by_id[pk], day, periods_by_room[pk]), room_by_id[pk])
        for pk in available_ids
    ]
    if not candidates:
        return {
            "price": None,
            "regularPrice": None,
            "priceKind": None,
            "hasPricePeriod": False,
            "periodLabel": "",
        }
    line, room = min(candidates, key=lambda item: (item[0]["roomPrice"], item[1].pk))
    kind = "regular"
    if line["hasPricePeriod"]:
        kind = "discount" if line["roomPrice"] < room.price else "seasonal"
    return {
        "price": inclusive_price(line["roomPrice"] * guests, percent),
        "regularPrice": inclusive_price(room.price * guests, percent),
        "priceKind": kind,
        "hasPricePeriod": line["hasPricePeriod"],
        "periodLabel": line["periodLabel"],
    }


class CalendarQuery(serializers.Serializer):
    resortId = serializers.CharField(max_length=64)
    category = serializers.ChoiceField(choices=["standard", "comfort", "suite"])
    roomId = serializers.CharField(max_length=64, required=False)
    month = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$")
    guests = serializers.IntegerField(min_value=1, max_value=4, default=1)
    arrival = serializers.DateField(required=False)


def availability_calendar(params):
    query = CalendarQuery(data=params)
    if set(params) - set(query.fields):
        raise Problem("Неизвестный параметр календаря.", 422)
    query.is_valid(raise_exception=True)
    data = query.validated_data
    resort = get_object_or_404(Resort, pk=data["resortId"], status="published")
    now = timezone.now()
    local_now = now.astimezone(ZoneInfo(resort.time_zone))
    today = local_now.date()
    try:
        first = date.fromisoformat(data["month"] + "-01")
    except ValueError as exc:
        raise Problem("Некорректный месяц.", 422) from exc
    horizon = today + timedelta(days=365)
    if not today.replace(day=1) <= first <= horizon.replace(day=1):
        raise Problem("Выберите месяц в пределах ближайшего года.", 422)
    last = (first + timedelta(days=32)).replace(day=1)
    arrival = data.get("arrival")
    if arrival and not today <= arrival <= horizon:
        raise Problem("Некорректная дата заезда.", 422)
    rooms = Room.objects.filter(resort=resort, category=data["category"], status="active")
    if data.get("roomId"):
        room = get_object_or_404(rooms, pk=data["roomId"])
        rooms = rooms.filter(pk=room.pk)
    eligible_rooms = list(
        rooms.filter(capacity__gte=data["guests"])
        .only("id", "price", "capacity")
        .prefetch_related(
            Prefetch(
                "price_periods",
                queryset=RoomPricePeriod.objects.filter(stay__overlap=Range(first, last, "[)")),
            )
        )
    )
    room_by_id = {room.pk: room for room in eligible_rooms}
    periods_by_room = {room.pk: list(room.price_periods.all()) for room in eligible_rooms}
    room_ids = set(room_by_id)
    # A single range query covers both the displayed month and a selected arrival.
    lower = min(first, arrival) if arrival else first
    occupied = list(
        BookingAllocation.objects.filter(
            active_allocation_inventory(now),
            room_id__in=room_ids,
            place__status="active",
            stay__overlap=Range(lower, last, "[)"),
        ).values_list("room_id", "place_id", "stay")
    )
    can_arrive_today = local_now < datetime.combine(
        today, resort.check_in_time, tzinfo=ZoneInfo(resort.time_zone)
    )
    guests_needed = data["guests"]
    days = []
    for offset in range((last - first).days):
        day = first + timedelta(days=offset)
        bookable = today <= day <= horizon and (day != today or can_arrive_today)
        available_ids = set()
        available_places = 0
        if bookable:
            busy_by_room = {}
            for r_id, place_id, stay in occupied:
                if stay.lower <= day < stay.upper:
                    busy_by_room.setdefault(r_id, set()).add(place_id)
            for r_id, rm in room_by_id.items():
                free_in_room = max(0, rm.capacity - len(busy_by_room.get(r_id, ())))
                if free_in_room >= guests_needed:
                    available_ids.add(r_id)
                    available_places += free_in_room
        departures = 0
        departure_places = 0
        if arrival and 0 < (day - arrival).days <= 30 and (arrival != today or can_arrive_today):
            blocked_by_room = {}
            for r_id, place_id, stay in occupied:
                if stay.lower < day and arrival < stay.upper:
                    blocked_by_room.setdefault(r_id, set()).add(place_id)
            for r_id, rm in room_by_id.items():
                continuous_free = max(0, rm.capacity - len(blocked_by_room.get(r_id, ())))
                if continuous_free >= guests_needed:
                    departures += 1
                    departure_places += continuous_free
        days.append(
            {
                "date": day.isoformat(),
                "availableRooms": len(available_ids),
                "availablePlaces": available_places,
                "departureRooms": departures,
                "departurePlaces": departure_places,
                "bookable": bookable,
                **available_price(
                    day,
                    available_ids,
                    room_by_id,
                    periods_by_room,
                    data["guests"],
                    resort.commission_percent,
                ),
            }
        )
    return {
        "month": data["month"],
        "today": today.isoformat(),
        "timeZone": resort.time_zone,
        "totalRooms": len(room_ids),
        "totalPlaces": sum(rm.capacity for rm in eligible_rooms),
        "days": days,
    }
