"""Explicit atomic seasonal-period application to the current rooms of one class."""

from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from psycopg.types.range import Range
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import bearer_or_csrf_protect
from .errors import Problem
from .guest_auth import enforce_limit
from .models import Audit, Resort, Room, RoomPricePeriod
from .serializers import PricePeriodInput
from .services import require_staff

MAX_ROOMS = 2000
CATEGORIES = ("standard", "comfort", "suite")


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Неизвестные поля запроса."]})
        return super().to_internal_value(data)


class RoomVersion(StrictInput):
    id = serializers.CharField(max_length=64)
    version = serializers.IntegerField(min_value=1)


class PeriodInput(PricePeriodInput, StrictInput):
    pass


class ClassPricingInput(StrictInput):
    category = serializers.ChoiceField(choices=CATEGORIES)
    resortVersion = serializers.IntegerField(min_value=1)
    rooms = RoomVersion(many=True, min_length=1, max_length=MAX_ROOMS)
    period = PeriodInput()

    def validate_rooms(self, value):
        if len({room["id"] for room in value}) != len(value):
            raise serializers.ValidationError("Номер указан несколько раз.")
        return value


def scoped_resort(request, pk):
    require_staff(request.user)
    resort = get_object_or_404(Resort.objects.select_for_update(), pk=pk)
    require_staff(request.user, resort.pk)
    return resort


def class_rooms(resort, category):
    rooms = list(
        Room.objects.filter(resort=resort, category=category)
        .order_by("number", "id")
        .prefetch_related("price_periods")[: MAX_ROOMS + 1]
    )
    if len(rooms) > MAX_ROOMS:
        raise Problem("В классе слишком много номеров для одной операции.", 409)
    return rooms


def preview_data(resort, category, rooms):
    return {
        "resortId": resort.pk,
        "resortVersion": resort.version,
        "category": category,
        "roomCount": len(rooms),
        "rooms": [
            {
                "id": room.pk,
                "number": room.number,
                "title": room.title,
                "status": room.status,
                "version": room.version,
                "pricePeriods": [
                    {
                        "label": p.label,
                        "start": p.stay.lower.isoformat(),
                        "end": p.stay.upper.isoformat(),
                        "price": p.price,
                    }
                    for p in room.price_periods.all()
                ],
            }
            for room in rooms
        ],
    }


@transaction.atomic
def preview(request, pk):
    if set(request.query_params) != {"category"}:
        raise Problem("Передайте только класс номера.", 422)
    category = serializers.ChoiceField(choices=CATEGORIES).run_validation(
        request.query_params.get("category")
    )
    resort = scoped_resort(request, pk)
    return preview_data(resort, category, class_rooms(resort, category))


@transaction.atomic
def apply_period(request, pk):
    resort = scoped_resort(request, pk)
    if resort.status == "archived":
        raise Problem("Санаторий в архиве.", 409)
    inp = ClassPricingInput(data=request.data)
    inp.is_valid(raise_exception=True)
    data = inp.validated_data
    rooms = class_rooms(resort, data["category"])
    expected = {entry["id"]: entry["version"] for entry in data["rooms"]}
    actual = {room.pk: room.version for room in rooms}
    if resort.version != data["resortVersion"] or expected != actual:
        raise Problem(
            "Состав класса или данные номеров изменились. Обновите список перед применением.",
            409,
            "class_pricing_stale",
        )
    period = data["period"]
    stay = Range(period["start"], period["end"], "[)")
    conflicts = []
    for room in rooms:
        periods = list(room.price_periods.all())
        if len(periods) >= 60 or any(
            p.stay.lower < period["end"] and period["start"] < p.stay.upper for p in periods
        ):
            conflicts.append(room.number)
    if conflicts:
        shown = ", ".join(conflicts[:8])
        raise Problem(
            f"Период пересекается с существующим или достигнут лимит периодов: № {shown}. "
            "Ни один номер не изменён. Проверьте периоды в редакторе номера.",
            409,
            "class_pricing_conflict",
        )
    RoomPricePeriod.objects.bulk_create(
        [
            RoomPricePeriod(room=room, label=period["label"], price=period["price"], stay=stay)
            for room in rooms
        ]
    )
    Room.objects.filter(pk__in=actual).update(version=F("version") + 1)
    Audit.objects.create(
        actor=request.user.name or request.user.username,
        resort=resort,
        entity="roomPricePeriods",
        entity_id=resort.pk,
        action="apply_to_class",
        label=f"Сезонная цена класса {data['category']}",
        before={"category": data["category"], "rooms": actual},
        after={
            "category": data["category"],
            "rooms": {pk: version + 1 for pk, version in actual.items()},
            "period": {
                **period,
                "start": period["start"].isoformat(),
                "end": period["end"].isoformat(),
            },
        },
    )
    return {
        "resortId": resort.pk,
        "category": data["category"],
        "appliedCount": len(rooms),
    }


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class ClassPricingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        return Response(preview(request, pk))

    def post(self, request, pk):
        enforce_limit(request, "class-pricing-write", ip_limit=30, minutes=5)
        return Response(apply_period(request, pk))
