"""Owned booking vouchers and staff attestation of collection at the property."""

from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from django.db import transaction
from django.http import HttpResponse
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
from booking.models import Booking, Resort
from booking.serializers import booking_data
from booking.services import guest_owner, log_change, require_staff, version_check

from .models import OnsiteSettlement
from .services import booking_payment_data, cancellation_terms, has_paid_booking
from .settlement import onsite_data, payment_terms

_font_lock = Lock()


def owned_booking(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("resort", "room"), pk=pk)
    if request.user.is_authenticated:
        require_staff(request.user, booking.resort_id, roles=("admin", "manager", "accountant"))
    elif booking.source != "website" or booking.owner != guest_owner(request):
        raise Problem("Бронирование не найдено.", 404)
    return booking


def voucher_data(booking):
    payment = booking_payment_data(booking)
    if not payment or payment.get("status") not in ("paid", "refunded", "partially_refunded"):
        raise Problem("Билет появится после подтверждения онлайн-оплаты.", 409)
    terms = cancellation_terms(booking)
    return {
        "number": "TYNYS-" + booking.pk.upper(),
        "bookingId": booking.pk,
        "guestName": booking.guest_label,
        "resortName": booking.snapshot.get("resortName", booking.resort.name),
        "roomName": booking.snapshot.get("roomName", booking.room.title),
        "unit": booking.snapshot.get("unit", booking.room.number),
        "start": booking.stay.lower.isoformat(),
        "end": booking.stay.upper.isoformat(),
        "guests": booking.guests,
        "status": booking.status,
        "paymentMode": payment.get("paymentMode", payment.get("environment", "demo")),
        "paymentTerms": payment_terms(booking),
        "onlinePaid": payment["amount"],
        "refundedAmount": payment.get("refundedAmount", 0),
        "onsitePayment": onsite_data(booking),
        "checkInTime": terms["checkInTime"],
        "timeZone": terms["timeZone"],
        "generatedAt": timezone.now().isoformat(),
    }


class OnsiteInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    method = serializers.ChoiceField(choices=["cash", "card"])
    received = serializers.BooleanField()

    def validate_received(self, value):
        if value is not True:
            raise serializers.ValidationError("Подтвердите фактическое получение оплаты.")
        return value

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["Неизвестные поля подтверждения оплаты."]}
            )
        return super().to_internal_value(data)


@transaction.atomic
def record_onsite(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    require_staff(request.user, booking.resort_id)
    resort = Resort.objects.select_for_update().get(pk=booking.resort_id)
    booking.refresh_from_db()
    inp = OnsiteInput(data=request.data)
    inp.is_valid(raise_exception=True)
    previous = OnsiteSettlement.objects.filter(booking=booking).first()
    if previous:
        if previous.method != inp.validated_data["method"]:
            raise Problem("Получение оплаты уже зарегистрировано другим способом.", 409)
        return booking
    version_check(booking, inp.validated_data)
    if booking.status != "confirmed" or not has_paid_booking(booking) or booking.checked_out_at:
        raise Problem("Подтверждение доступно для оплаченной брони до выезда.", 409)
    today = timezone.now().astimezone(ZoneInfo(resort.time_zone)).date()
    if not booking.stay.lower <= today < booking.stay.upper:
        raise Problem("Оплату на месте можно подтвердить только в даты проживания.", 409)
    amount = payment_terms(booking)["onsiteAmount"]
    if amount <= 0:
        raise Problem("По этой брони нет суммы к оплате на месте.", 409)
    before = booking_data(booking, staff=True)
    OnsiteSettlement.objects.create(
        booking=booking,
        amount=amount,
        method=inp.validated_data["method"],
        recorded_by=request.user,
    )
    # Clear a cached missing reverse relation from the before snapshot.
    booking.refresh_from_db()
    booking.version += 1
    booking.save(update_fields=["version"])
    log_change(
        request.user,
        "bookings",
        booking,
        "onsite_payment_recorded",
        before,
        booking_data(booking, staff=True),
        booking.resort_id,
    )
    return booking


def voucher_pdf(data):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    with _font_lock:
        if "TynysVoucher" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(
                TTFont("TynysVoucher", str(Path(__file__).parent / "fonts/NotoSans-Regular.ttf"))
            )
    style = ParagraphStyle("voucher", fontName="TynysVoucher", fontSize=10, leading=16)
    title = ParagraphStyle("voucherTitle", parent=style, fontSize=21, leading=28)

    def para(value, s=style):
        return Paragraph(escape(str(value)), s)

    def money(value):
        return f"{value:,} KZT".replace(",", " ")

    terms = data["paymentTerms"]
    state = "ДЕЙСТВУЕТ" if data["status"] == "confirmed" else "ОТМЕНЁН / НЕ ДЕЙСТВУЕТ"
    rows = [
        ("Гость", data["guestName"]),
        ("Санаторий", data["resortName"]),
        ("Номер", f"{data['roomName']} · № {data['unit']}"),
        ("Проживание", f"{data['start']} — {data['end']}"),
        ("Заезд", f"{data['checkInTime']} ({data['timeZone']})"),
        ("Гостей", data["guests"]),
        ("Общая стоимость", money(terms["total"])),
        ("Получено онлайн", money(data["onlinePaid"])),
        ("Возвращено онлайн", money(data["refundedAmount"])),
        ("Оплата в санатории", money(terms["onsiteAmount"])),
        (
            "Получение в санатории",
            "Подтверждено сотрудником"
            if data["onsitePayment"]["status"] == "recorded"
            else "Ещё не подтверждено",
        ),
    ]
    table = Table([[para(k), para(v)] for k, v in rows], colWidths=[185, 300])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dfe7e1")),
            ]
        )
    )
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=45, bottomMargin=45
    )
    story = [
        para("Тыныс · Билет бронирования", title),
        Spacer(1, 14),
        para(data["number"]),
        para(state),
        Spacer(1, 18),
        table,
        Spacer(1, 18),
        para(
            "Предъявите билет сотруднику санатория. Актуальный статус проверяется в кабинете сотрудника по номеру бронирования. Это подтверждение бронирования, не банковский или фискальный чек."
        ),
    ]
    if data["paymentMode"] != "production":
        story.insert(0, para("ДЕМОНСТРАЦИЯ — без реальных денежных операций"))
    doc.build(story)
    return output.getvalue()


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class VoucherView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk, pdf=False):
        data = voucher_data(owned_booking(request, pk))
        if not pdf:
            return Response(data)
        response = HttpResponse(voucher_pdf(data), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{data["number"]}.pdf"'
        return response


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class OnsitePaymentView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        return Response(booking_data(record_onsite(request, pk), staff=True))
