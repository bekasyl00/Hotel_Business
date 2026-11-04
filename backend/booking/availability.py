"""Bounded public availability counts; no booking or guest details leave this module."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.shortcuts import get_object_or_404
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework import serializers

from .errors import Problem
from .holds import active_inventory
from .models import Booking, Resort, Room


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
    room_ids = set(rooms.filter(capacity__gte=data["guests"]).values_list("id", flat=True))
    # A single range query covers both the displayed month and a selected arrival.
    lower = min(first, arrival) if arrival else first
    occupied = list(
        Booking.objects.filter(
            active_inventory(now), room_id__in=room_ids, stay__overlap=Range(lower, last, "[)")
        ).values_list("room_id", "stay")
    )
    can_arrive_today = local_now < datetime.combine(
        today, resort.check_in_time, tzinfo=ZoneInfo(resort.time_zone)
    )
    days = []
    for offset in range((last - first).days):
        day = first + timedelta(days=offset)
        busy = {room_id for room_id, stay in occupied if stay.lower <= day < stay.upper}
        bookable = today <= day <= horizon and (day != today or can_arrive_today)
        departures = 0
        if arrival and 0 < (day - arrival).days <= 30:
            blocked = {
                room_id for room_id, stay in occupied if stay.lower < day and arrival < stay.upper
            }
            if arrival != today or can_arrive_today:
                departures = len(room_ids - blocked)
        days.append(
            {
                "date": day.isoformat(),
                "availableRooms": len(room_ids - busy) if bookable else 0,
                "departureRooms": departures,
                "bookable": bookable,
            }
        )
    return {
        "month": data["month"],
        "today": today.isoformat(),
        "timeZone": resort.time_zone,
        "totalRooms": len(room_ids),
        "days": days,
    }
