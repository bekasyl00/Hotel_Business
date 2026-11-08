"""A signed ticket locates a booking; staff authorization still controls arrival."""

from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from booking.authentication import bearer_or_csrf_protect
from booking.errors import Problem
from booking.guest_auth import enforce_limit
from booking.models import Booking, Resort
from booking.serializers import booking_data
from booking.services import change_stay, require_staff, version_check

from .services import has_paid_booking
from .settlement import payment_terms

PREFIX = "TYNYS1."
SALT = "tynys.booking.arrival.v1"


def ticket_code(booking):
    if booking.status != "confirmed" or booking.checked_out_at or not has_paid_booking(booking):
        return None
    # Only an opaque booking id, never names, phone numbers or document identities.
    return PREFIX + signing.Signer(salt=SALT).sign(booking.pk)


def booking_id_from_code(value):
    try:
        if value.startswith(PREFIX):
            value = signing.Signer(salt=SALT).unsign(value[len(PREFIX) :])
        elif value.upper().startswith("TYNYS-"):
            value = value[6:]
        return str(UUID(value))
    except (signing.BadSignature, ValueError, TypeError):
        raise Problem(
            "Не удалось прочитать билет. Проверьте QR или номер бронирования.",
            422,
            "ticket_invalid",
        ) from None


def arrival_state(booking):
    if booking.status != "confirmed" or not has_paid_booking(booking):
        return "inactive"
    if booking.checked_out_at:
        return "departed"
    if booking.checked_in_at:
        return "accepted"
    today = timezone.now().astimezone(ZoneInfo(booking.resort.time_zone)).date()
    if not booking.stay.lower <= today < booking.stay.upper:
        return "outside_dates"
    return "ready"


class ResolveInput(serializers.Serializer):
    code = serializers.CharField(max_length=256, allow_blank=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {"code"}:
            raise serializers.ValidationError({"non_field_errors": ["Укажите только код билета."]})
        return super().to_internal_value(data)


class ArrivalInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    received = serializers.BooleanField()
    method = serializers.ChoiceField(choices=["cash", "card"])

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["Неизвестные поля подтверждения заезда."]}
            )
        return super().to_internal_value(data)


@transaction.atomic
def accept_arrival(request, pk):
    require_staff(request.user)
    booking = get_object_or_404(Booking, pk=pk)
    require_staff(request.user, booking.resort_id)
    Resort.objects.select_for_update().get(pk=booking.resort_id)
    booking.refresh_from_db()
    inp = ArrivalInput(data=request.data)
    inp.is_valid(raise_exception=True)
    state = arrival_state(booking)
    if state == "accepted":
        return booking
    version_check(booking, inp.validated_data)
    if state != "ready":
        raise Problem(
            "Заезд недоступен: проверьте оплату, статус и даты брони.", 409, "arrival_unavailable"
        )
    if payment_terms(booking)["onsiteAmount"] > 0 and not hasattr(booking, "onsite_settlement"):
        from .vouchers import record_onsite

        booking = record_onsite(SimpleNamespace(user=request.user, data=inp.validated_data), pk)
    # Both collection and check-in commit together or neither does.
    return change_stay(
        SimpleNamespace(user=request.user, data={"version": booking.version}), pk, "check-in"
    )


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class ArrivalResolveView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        require_staff(request.user)
        enforce_limit(
            request, "arrival-scan", str(request.user.pk), phone_limit=120, ip_limit=300, minutes=1
        )
        inp = ResolveInput(data=request.data)
        inp.is_valid(raise_exception=True)
        pk = booking_id_from_code(inp.validated_data["code"])
        booking = get_object_or_404(Booking.objects.select_related("resort", "room"), pk=pk)
        require_staff(request.user, booking.resort_id)
        state = arrival_state(booking)
        # A cancelled or unpaid ticket never returns an actionable voucher.
        if state == "inactive":
            raise Problem(
                "Билет не действует или онлайн-оплата не подтверждена.", 409, "ticket_inactive"
            )
        from .vouchers import voucher_data

        return Response(
            {
                "voucher": voucher_data(booking),
                "booking": booking_data(booking, staff=True),
                "state": state,
            }
        )


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class ArrivalAcceptView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        return Response(booking_data(accept_arrival(request, pk), staff=True))
