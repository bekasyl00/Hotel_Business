from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers

from booking.errors import Problem
from booking.models import Audit, Resort
from booking.services import require_staff, version_check
from commerce.models import AccountingCompany, AccountingDocument, AccountingSequence
from commerce.services import booking_payment_data

KINDS = ("invoice", "act", "cash_order")


def require_accountant(user, resort_id=None):
    require_staff(user, resort_id, roles=("admin", "accountant"))


def resorts_for(user):
    require_accountant(user)
    return Resort.objects.all()


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Неизвестные поля запроса."]})
        return super().to_internal_value(data)


class CompanyInput(StrictInput):
    version = serializers.IntegerField(min_value=0)
    supplier = serializers.CharField(max_length=160)
    bin = serializers.RegexField(r"^[0-9]{12}$")
    address = serializers.CharField(max_length=240)
    iban = serializers.RegexField(r"^KZ[A-Z0-9]{18}$", allow_blank=True, default="")
    bank = serializers.CharField(max_length=100, allow_blank=True, default="")
    bik = serializers.RegexField(r"^[A-Z0-9]{8}([A-Z0-9]{3})?$", allow_blank=True, default="")
    director = serializers.CharField(max_length=100, allow_blank=True, default="")
    accountant = serializers.CharField(max_length=100, allow_blank=True, default="")
    vatMode = serializers.ChoiceField(choices=["no_vat", "included"])
    vatRate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, default=0
    )

    def validate(self, data):
        if (data["vatMode"] == "included") != (data["vatRate"] > 0):
            raise serializers.ValidationError(
                "Укажите ставку для включённого НДС; без НДС ставка равна нулю."
            )
        return data


def company_data(resort):
    item = AccountingCompany.objects.filter(resort=resort).first()
    return {
        "resortId": resort.pk,
        "version": item.version if item else 0,
        **(item.details if item else {}),
    }


@transaction.atomic
def save_company(request, resort_id):
    require_accountant(request.user, resort_id)
    resort = get_object_or_404(Resort.objects.select_for_update(), pk=resort_id)
    inp = CompanyInput(data=request.data)
    inp.is_valid(raise_exception=True)
    values = dict(inp.validated_data)
    version = values.pop("version")
    item = AccountingCompany.objects.filter(resort=resort).first()
    if version != (item.version if item else 0):
        raise Problem("Реквизиты уже изменены. Обновите страницу.", 409)
    values["vatRate"] = str(values["vatRate"])
    if item:
        item.details, item.version = values, item.version + 1
        item.save()
    else:
        item = AccountingCompany.objects.create(resort=resort, details=values)
    Audit.objects.create(
        actor=request.user.name or request.user.username,
        resort=resort,
        entity="accountingCompany",
        entity_id=resort.pk,
        action="update",
        label="Реквизиты организации",
        before={"version": version},
        after={"version": item.version},
    )
    return company_data(resort)


def document_data(doc):
    return {
        "id": doc.pk,
        "bookingId": doc.booking_id,
        "resortId": doc.booking.resort_id,
        "kind": doc.kind,
        "state": doc.state,
        "number": doc.number,
        "version": doc.version,
        "guest": doc.snapshot.get("guest", ""),
        "amount": doc.snapshot.get("amount", 0),
        "paymentMode": doc.snapshot.get("paymentMode", "unpaid"),
        "createdAt": doc.created_at.isoformat(),
        "releasedAt": doc.released_at.isoformat() if doc.released_at else None,
    }


def snapshot(booking, number):
    from commerce.settlement import payment_terms

    company = AccountingCompany.objects.filter(resort=booking.resort).first()
    details = company.details if company else {}
    total = int(booking.snapshot.get("total", 0))
    vat = None
    if details.get("vatMode") == "no_vat":
        vat = Decimal(0)
    elif details.get("vatMode") == "included":
        rate = Decimal(details["vatRate"])
        vat = (Decimal(total) * rate / (100 + rate)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    payment = booking_payment_data(booking)
    terms = payment_terms(booking)
    split_payment = terms["version"] == 1
    onsite = getattr(booking, "onsite_settlement", None)
    online_paid = (
        payment.get("amount", 0)
        if payment and payment.get("status") in ("paid", "refunded", "partially_refunded")
        else 0
    )
    online_refunded = payment.get("refundedAmount", 0) if payment else 0
    now = timezone.now().astimezone(ZoneInfo(booking.resort.time_zone))
    return {
        "schema": 1,
        "number": number,
        "date": now.strftime("%d.%m.%Y"),
        "service_date": booking.checked_out_at.astimezone(
            ZoneInfo(booking.resort.time_zone)
        ).strftime("%d.%m.%Y")
        if booking.checked_out_at
        else "",
        "guest": booking.guest_label,
        "supplier": details.get("supplier", booking.resort.name),
        **{
            key: details.get(key, "")
            for key in ["bin", "address", "iban", "bank", "bik", "director", "accountant"]
        },
        "service": f"Услуги проживания: {booking.stay.lower:%d.%m.%Y}–{booking.stay.upper:%d.%m.%Y}; {booking.snapshot.get('roomName', booking.room.number)}",
        "quantity": 1,
        "unit_price": total,
        "amount": total,
        "net": str(Decimal(total) - vat) if vat is not None else "",
        "vat": str(vat) if vat is not None else "",
        "vat_label": "Без НДС"
        if details.get("vatMode") == "no_vat"
        else (details.get("vatRate", "") + "%" if vat is not None else "Не настроен"),
        "paymentMode": payment.get("paymentMode", "unpaid") if payment else "unpaid",
        "paidAmount": (onsite.amount if onsite else 0) if split_payment else online_paid,
        "refundedAmount": 0 if split_payment else online_refunded,
        "customerTotal": terms["total"],
        "platformFeeAmount": terms["onlineAmount"] if split_payment else 0,
        "platformFeePaidAmount": online_paid if split_payment else 0,
        "platformFeeRefundedAmount": online_refunded if split_payment else 0,
        "onsiteAmount": terms["onsiteAmount"],
        "paymentEvidence": ("staff_attestation" if onsite else "not_recorded")
        if split_payment
        else "online_payment",
        "paymentTerms": terms,
        "checkedOutAt": booking.checked_out_at.isoformat() if booking.checked_out_at else None,
        "companyVersion": company.version if company else 0,
    }


@transaction.atomic
def prepare_document(booking, kind, user):
    # Callers own authorization; auto-preparation is triggered only by recorded checkout.
    if kind not in KINDS:
        raise Problem("Неизвестный шаблон.")
    Resort.objects.select_for_update().get(pk=booking.resort_id)
    existing = (
        AccountingDocument.objects.filter(booking=booking, kind=kind)
        .exclude(state="voided")
        .first()
    )
    if existing:
        return existing
    year = timezone.now().astimezone(ZoneInfo(booking.resort.time_zone)).year
    sequence, _ = AccountingSequence.objects.get_or_create(
        resort=booking.resort, year=year, kind=kind
    )
    number = f"{ {'invoice': 'SF', 'act': 'ACT', 'cash_order': 'PKO'}[kind] }-{year}-{sequence.next_value:06d}"
    sequence.next_value += 1
    sequence.save(update_fields=["next_value"])
    doc = AccountingDocument.objects.create(
        booking=booking,
        kind=kind,
        number=number,
        snapshot=snapshot(booking, number),
        created_by=user,
    )
    audit_document(doc, user, "prepare")
    return doc


def prepare_after_stay(booking, user):
    for kind in ("invoice", "act"):
        prepare_document(booking, kind, user)


def audit_document(doc, user, action):
    Audit.objects.create(
        actor=user.name or user.username,
        resort_id=doc.booking.resort_id,
        entity="accountingDocuments",
        entity_id=doc.pk,
        action=action,
        label=doc.number,
        after={"state": doc.state, "kind": doc.kind, "version": doc.version},
    )


@transaction.atomic
def change_document(request, pk, action):
    require_accountant(request.user)
    doc = get_object_or_404(
        AccountingDocument.objects.select_related("booking__resort", "booking__room"),
        pk=pk,
        booking__resort__in=resorts_for(request.user),
    )
    Resort.objects.select_for_update().get(pk=doc.booking.resort_id)
    doc.refresh_from_db()
    doc.booking.refresh_from_db()
    if set(request.data) != {"version"}:
        raise Problem("Передайте только версию документа.")
    version_check(doc, request.data)
    if action == "void":
        if doc.state == "voided":
            raise Problem("Документ уже отменён.", 409)
        doc.state, doc.voided_at = "voided", timezone.now()
    elif action in ("refresh", "release"):
        if doc.state != "draft":
            raise Problem("Опубликованный документ неизменяем; отмените и создайте новый.", 409)
        if action == "release":
            if doc.kind == "cash_order":
                raise Problem(
                    "ПКО требует подтверждённого учёта наличных; банковская оплата его не заменяет.",
                    409,
                )
            if not doc.booking.checked_out_at or doc.booking.status != "confirmed":
                raise Problem(
                    "Документы доступны гостю после фактического завершения проживания.", 409
                )
            details = company_data(doc.booking.resort)
            if not all(details.get(k) for k in ["supplier", "bin", "address", "vatMode"]):
                raise Problem("Сначала заполните реквизиты и настройки НДС.", 409)
            payment = booking_payment_data(doc.booking)
            if not payment or payment.get("status") != "paid" or payment.get("refundStatus"):
                raise Problem("Сначала завершите сверку оплаты и возвратов.", 409)
            from commerce.settlement import payment_terms

            terms = payment_terms(doc.booking)
            onsite = getattr(doc.booking, "onsite_settlement", None)
            if (
                terms["version"] == 1
                and terms["onsiteAmount"] > 0
                and (onsite is None or onsite.amount != terms["onsiteAmount"])
            ):
                raise Problem(
                    "Сначала сотрудник должен отметить оплату проживания в санатории.", 409
                )
            doc.state, doc.released_at = "released", timezone.now()
        doc.snapshot = snapshot(doc.booking, doc.number)
    else:
        raise Problem("Не найдено.", 404)
    doc.version += 1
    doc.save()
    audit_document(doc, request.user, action)
    return document_data(doc)


def period(params):
    end = serializers.DateField().run_validation(
        params.get("end", timezone.localdate().isoformat())
    )
    start = serializers.DateField().run_validation(
        params.get("start", (end - timedelta(days=29)).isoformat())
    )
    if end < start or (end - start).days > 365 or start.year < 2000 or end.year > 2100:
        raise Problem("Период должен составлять от 1 до 366 дней.")
    return start, end
