from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from django.db import transaction
from django.shortcuts import get_object_or_404

from booking.errors import Problem
from booking.models import Resort

from .models import DemoPayment, DemoRefund

NOTICE = (
    "ДЕМОНСТРАЦИОННАЯ КВИТАНЦИЯ. Деньги не списывались. "
    "Это не фискальный чек и не документ банка Kaspi."
)
_font_lock = Lock()


def freeze_receipt(payment, *, legacy=False):
    from .services import cancellation_terms

    b = payment.booking
    snapshot = b.snapshot
    return {
        "number": f"DEMO-{payment.created_at:%Y%m%d}-{payment.id.replace('-', '')[:12].upper()}",
        "issuedAt": payment.created_at.isoformat(),
        "paymentId": payment.id,
        "bookingId": b.id,
        "resortName": snapshot.get("resortName", b.resort.name),
        "resortAddress": snapshot.get("resortAddress", b.resort.address),
        "roomName": snapshot.get("roomName", b.room.title),
        "unit": snapshot.get("unit", b.room.number),
        "start": b.stay.lower.isoformat(),
        "end": b.stay.upper.isoformat(),
        "guests": b.guests,
        "guestLabel": b.guest_label,
        "tariffName": snapshot.get("tariffName", b.tariff.name),
        "regularNightly": snapshot.get("regularNightly", snapshot.get("nightly")),
        "nightly": snapshot.get("nightly"),
        "nights": snapshot.get("nights", (b.stay.upper - b.stay.lower).days),
        "discountPercent": snapshot.get("discountPercent", 0),
        "total": payment.amount,
        "currency": "KZT",
        "checkinAt": cancellation_terms(b)["checkinAt"],
        "timeZone": cancellation_terms(b)["timeZone"],
        "paymentMode": "demo",
        "source": "demo",
        "notice": NOTICE,
        "legacySnapshot": legacy,
    }


@transaction.atomic
def receipt_for_request(request, pk):
    from booking.services import admin, guest_owner

    from .services import payment_data

    payment = get_object_or_404(
        DemoPayment.objects.select_related("booking__resort", "booking__room", "booking__tariff"),
        pk=pk,
        outcome="success",
    )
    b = payment.booking
    owns = b.source == "website" and b.owner == guest_owner(request)
    employee = request.user.is_authenticated and (
        admin(request.user) or request.user.resort_id == b.resort_id
    )
    if not owns and not employee:
        raise Problem("Квитанция не найдена.", 404)
    Resort.objects.select_for_update().get(pk=b.resort_id)
    payment.refresh_from_db()
    if not payment.receipt:
        payment.receipt = freeze_receipt(payment, legacy=True)
        payment.save(update_fields=["receipt"])
    refund = DemoRefund.objects.filter(payment=payment).first()
    return {
        "receipt": payment.receipt,
        "payment": payment_data(payment),
        "refund": {
            "amount": refund.amount,
            "percent": refund.percent,
            "createdAt": refund.created_at.isoformat(),
        }
        if refund
        else None,
    }


def receipt_pdf(payload):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    with _font_lock:
        if "TynysNoto" not in pdfmetrics.getRegisteredFontNames():
            fonts = Path(__file__).parent / "fonts"
            pdfmetrics.registerFont(TTFont("TynysNoto", str(fonts / "NotoSans-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("TynysNotoBold", str(fonts / "NotoSans-Bold.ttf")))
    body = ParagraphStyle("body", fontName="TynysNoto", fontSize=10, leading=15)
    title = ParagraphStyle("title", parent=body, fontName="TynysNotoBold", fontSize=19, leading=26)
    heading = ParagraphStyle(
        "heading", parent=body, fontName="TynysNotoBold", fontSize=12, leading=18
    )
    muted = ParagraphStyle("muted", parent=body, textColor=colors.HexColor("#596860"), fontSize=9)
    r = payload["receipt"]
    document = BytesIO()
    doc = SimpleDocTemplate(
        document,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Тыныс · {r['number']}",
        author="Тыныс",
    )

    def para(value, style=body):
        return Paragraph(escape(str(value if value is not None else "—")), style)

    def money(value):
        return f"{int(value):,} ₸".replace(",", " ") if value is not None else "—"

    def dated(value):
        return (
            datetime.fromisoformat(value)
            .astimezone(ZoneInfo(r["timeZone"]))
            .strftime("%d.%m.%Y %H:%M %z")
        )

    rows = [
        ("Номер квитанции", r["number"]),
        ("Дата операции", dated(r["issuedAt"])),
        ("Бронирование", r["bookingId"]),
        ("Санаторий", r["resortName"]),
        ("Адрес", r["resortAddress"]),
        ("Номер", f"{r['unit']} · {r['roomName']}"),
        ("Гость", r["guestLabel"]),
        ("Количество гостей", r["guests"]),
        ("Проживание", f"{r['start']} — {r['end']} · ночей: {r['nights']}"),
        ("Время заезда", f"{dated(r['checkinAt'])} · {r['timeZone']}"),
        ("Тариф", r["tariffName"]),
        ("Обычная цена / ночь", money(r["regularNightly"])),
        ("Скидка", f"{r['discountPercent']}%"),
        ("Цена / ночь", money(r["nightly"])),
        ("Демо-оплата", money(r["total"])),
    ]
    table = Table(
        [[para(label, muted), para(value)] for label, value in rows], colWidths=[55 * mm, 115 * mm]
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8e4")),
            ]
        )
    )
    story = [
        para("Тыныс · квитанция", title),
        Spacer(1, 5 * mm),
        para(r["notice"], heading),
        Spacer(1, 6 * mm),
        table,
    ]
    if r.get("legacySnapshot"):
        story += [
            Spacer(1, 4 * mm),
            para(
                "Архивная операция: данные восстановлены из бронирования; адрес и недостающие сведения зафиксированы при первом открытии квитанции.",
                muted,
            ),
        ]
    if payload["refund"]:
        refund = payload["refund"]
        story += [
            Spacer(1, 6 * mm),
            para("Сведения об отмене и возврате", heading),
            para(
                f"Дата: {dated(refund['createdAt'])}. Демонстрационный возврат: {money(refund['amount'])} ({refund['percent']}%)."
            ),
            para("Исходная сумма оплаты выше сохранена. Реальные деньги не перечислялись.", muted),
        ]
    doc.build(story)
    return document.getvalue()
