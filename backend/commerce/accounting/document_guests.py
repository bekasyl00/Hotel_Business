"""Staff-only guest document roster, isolated from booking/profile identity and pricing."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from booking.authentication import bearer_or_csrf_protect
from booking.errors import Problem
from booking.guest_auth import enforce_limit
from booking.models import Audit, Booking, GuestAccount, Resort
from booking.services import require_staff
from commerce.models import DocumentGuestRoster

from .private_data import seal, unseal
from .services import StrictInput

FIELDS = ("fullName", "iin", "address", "phone", "iban", "bank", "bik")


class GuestInput(StrictInput):
    fullName = serializers.CharField(max_length=160, allow_blank=True, default="")
    iin = serializers.RegexField(r"^[0-9]{12}$", allow_blank=True, default="")
    address = serializers.CharField(max_length=240, allow_blank=True, default="")
    phone = serializers.RegexField(r"^\+?[0-9 ()-]{5,32}$", allow_blank=True, default="")
    iban = serializers.RegexField(r"^KZ[A-Z0-9]{18}$", allow_blank=True, default="")
    bank = serializers.CharField(max_length=100, allow_blank=True, default="")
    bik = serializers.RegexField(r"^[A-Z0-9]{8}([A-Z0-9]{3})?$", allow_blank=True, default="")


class RosterInput(StrictInput):
    version = serializers.IntegerField(min_value=0)
    buyerIndex = serializers.IntegerField(min_value=0, allow_null=True)
    guests = GuestInput(many=True, max_length=4)

    def validate(self, data):
        if data["buyerIndex"] is not None and data["buyerIndex"] >= len(data["guests"]):
            raise serializers.ValidationError({"buyerIndex": "Выберите плательщика из списка."})
        if len(data["guests"]) > self.context["booking"].guests:
            raise serializers.ValidationError({"guests": "Число гостей превышает бронь."})
        return data


def primary_guest(booking):
    # Only the explicit profile relation and owner may identify an account.
    # A contact number/name in a manual booking is not an account association.
    account = (
        GuestAccount.objects.select_related("profile")
        .filter(profile_id=booking.guest_profile_id, profile__owner=booking.owner)
        .first()
        if booking.guest_profile_id
        else None
    )
    metadata = {
        "index": 0,
        "source": "profile" if account else "manual",
        "lockedFields": ["fullName", "phone"] if account else [],
    }
    contacts = {
        "fullName": account.profile.name if account else booking.guest_label,
        "phone": account.phone if account else booking.guest_phone,
    }
    return metadata, contacts


def with_primary_contacts(booking, payload):
    metadata, contacts = primary_guest(booking)
    guests = [dict(guest) for guest in payload["guests"]]
    if not guests:
        guests.append({**dict.fromkeys(FIELDS, ""), **contacts})
    elif metadata["source"] == "profile":
        guests[0].update(contacts)
    return {**payload, "guests": guests}


def read_payload(booking):
    row = DocumentGuestRoster.objects.filter(booking=booking).first()
    data = (
        unseal(row.ciphertext, context=f"roster:{booking.pk}")
        if row
        else {"guests": [], "buyerIndex": None}
    )
    return row, with_primary_contacts(booking, data)


def missing_fields(booking, payload):
    missing = []
    guests, buyer = payload["guests"], payload["buyerIndex"]
    if len(guests) != booking.guests:
        missing.append("guests")
    for index, guest in enumerate(guests):
        for field in ("fullName", "iin"):
            if not guest.get(field):
                missing.append(f"guests.{index}.{field}")
    if buyer is None or buyer >= len(guests):
        missing.append("buyerIndex")
    elif not guests[buyer].get("address"):
        missing.append(f"guests.{buyer}.address")
    return missing


def roster_data(booking, row, payload):
    metadata, _ = primary_guest(booking)
    missing = missing_fields(booking, payload)
    return {
        "bookingId": booking.pk,
        "version": row.version if row else 0,
        "expectedGuests": booking.guests,
        "primaryGuest": metadata,
        **payload,
        "complete": not missing,
        "missing": missing,
        "updatedAt": row.updated_at.isoformat() if row else None,
    }


def audit_access(booking, user, action, version, count):
    Audit.objects.create(
        actor=user.name or user.username,
        resort=booking.resort,
        entity="documentGuests",
        entity_id=booking.pk,
        action=action,
        label="Реквизиты гостей для документов",
        after={"version": version, "count": count, "fields": list(FIELDS)},
    )


def authorized_booking(request, pk):
    require_staff(request.user, roles=("admin", "manager"))
    booking = get_object_or_404(Booking.objects.select_related("resort"), pk=pk)
    require_staff(request.user, booking.resort_id, roles=("admin", "manager"))
    return booking


@transaction.atomic
def save_roster(request, pk):
    booking = authorized_booking(request, pk)
    Resort.objects.select_for_update().get(pk=booking.resort_id)
    booking.refresh_from_db()
    inp = RosterInput(data=request.data, context={"booking": booking})
    inp.is_valid(raise_exception=True)
    values = dict(inp.validated_data)
    version = values.pop("version")
    values = with_primary_contacts(booking, values)
    row = DocumentGuestRoster.objects.filter(booking=booking).first()
    if version != (row.version if row else 0):
        raise Problem("Реквизиты уже изменены. Обновите данные.", 409)
    encrypted = seal(values, context=f"roster:{booking.pk}")
    if row:
        row.ciphertext, row.updated_by, row.version = encrypted, request.user, row.version + 1
        row.save()
    else:
        row = DocumentGuestRoster.objects.create(
            booking=booking, ciphertext=encrypted, updated_by=request.user
        )
    audit_access(
        booking, request.user, "document_guests_updated", row.version, len(values["guests"])
    )
    return roster_data(booking, row, values)


def buyer_snapshot(booking, number):
    row, payload = read_payload(booking)
    buyer_index = payload["buyerIndex"]
    if row is None or buyer_index is None:
        return {}
    return {
        "documentGuestVersion": row.version,
        "buyerEncrypted": seal(
            payload["guests"][buyer_index], context=f"buyer:{booking.pk}:{number}"
        ),
    }


def require_complete_roster(booking):
    _, payload = read_payload(booking)
    if missing_fields(booking, payload):
        raise Problem(
            "Заполните ФИО и ИИН каждого гостя, выберите плательщика и укажите его адрес.",
            409,
            "document_guests_incomplete",
        )


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class DocumentGuestsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        enforce_limit(request, "document-guests-read", ip_limit=120, minutes=5)
        return self.read(request, pk)

    @transaction.atomic
    def read(self, request, pk):
        booking = authorized_booking(request, pk)
        row, payload = read_payload(booking)
        audit_access(
            booking,
            request.user,
            "document_guests_read",
            row.version if row else 0,
            len(payload["guests"]),
        )
        return Response(roster_data(booking, row, payload))

    def put(self, request, pk):
        enforce_limit(request, "document-guests-write", ip_limit=60, minutes=5)
        return Response(save_roster(request, pk))
