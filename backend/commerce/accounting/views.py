import csv
from datetime import datetime, time, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.http import HttpResponse
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
from booking.models import Booking
from booking.services import admin, guest_owner, require_staff
from commerce.models import AccountingDocument, DemoPayment, DemoRefund, PaymentEvent, RefundRequest
from commerce.services import booking_payment_data

from . import services as svc
from .expenses import create_expense, void_expense
from .rendering import pdf_bytes, xlsx_bytes
from .reporting import financial_report, report_xlsx


def bookings_data(query):
    from commerce.settlement import onsite_data, payment_terms

    rows = []
    for b in query.select_related(
        "resort", "room", "bank_payment__refund", "onsite_settlement"
    ).prefetch_related("demo_payments"):
        terms = payment_terms(b)
        onsite = onsite_data(b)
        rows.append(
            {
                "id": b.pk,
                "resortId": b.resort_id,
                "resort": b.resort.name,
                "guest": b.guest_label,
                "room": b.snapshot.get("roomName", b.room.number),
                "start": b.stay.lower.isoformat(),
                "end": b.stay.upper.isoformat(),
                "amount": b.snapshot.get("total", 0),
                "customerTotal": terms["total"],
                "onlineAmount": terms["onlineAmount"],
                "onsiteAmount": terms["onsiteAmount"],
                "onsitePayment": onsite,
                "status": b.status,
                "completed": bool(b.checked_out_at),
                "payment": booking_payment_data(b),
            }
        )
    return rows


def window(params):
    start, end = svc.period(params)
    tz = ZoneInfo("Asia/Almaty")
    return (
        start,
        end,
        datetime.combine(start, time.min, tz),
        datetime.combine(end + timedelta(days=1), time.min, tz),
    )


def scope(request):
    resorts = svc.resorts_for(request.user)
    resort_id = request.query_params.get("resortId")
    if resort_id:
        get_object_or_404(resorts, pk=resort_id)
        resorts = resorts.filter(pk=resort_id)
    return resorts


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class AccountingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, resource="overview", pk=None, format_kind=None):
        resorts = scope(request)
        if resource in ("file", "report", "export"):
            enforce_limit(request, "accounting-download", ip_limit=60, minutes=5)
        if resource == "company":
            return Response(svc.company_data(get_object_or_404(resorts, pk=pk)))
        if resource == "file":
            doc = get_object_or_404(
                AccountingDocument.objects.select_related("booking"),
                pk=pk,
                booking__resort__in=resorts,
            )
            return download(doc, format_kind)
        start, end, lower, upper = window(request.query_params)
        mode = serializers.ChoiceField(choices=["production", "sandbox", "demo"]).run_validation(
            request.query_params.get("paymentMode", "production")
        )
        bookings = Booking.objects.filter(
            resort__in=resorts, created_at__gte=lower, created_at__lt=upper
        )
        # Unpaid reservations remain visible; financial rows never mix environments.
        bookings = bookings.filter(
            Q(bank_payment__environment=mode)
            | (
                Q(bank_payment__isnull=True)
                if mode == "demo"
                else Q(bank_payment__isnull=True, demo_payments__isnull=True)
            )
        ).distinct()
        search = request.query_params.get("search", "")
        if len(search) > 100:
            raise Problem("Поиск: не более 100 символов.")
        if search:
            bookings = bookings.filter(Q(guest_label__icontains=search) | Q(id__icontains=search))
        if mode == "demo":
            payments = DemoPayment.objects.filter(
                booking__resort__in=resorts,
                outcome="success",
                created_at__gte=lower,
                created_at__lt=upper,
            )
            refunds = DemoRefund.objects.filter(
                payment__booking__resort__in=resorts, created_at__gte=lower, created_at__lt=upper
            )
        else:
            payments = PaymentEvent.objects.filter(
                payment__booking__resort__in=resorts,
                environment=mode,
                kind="charge",
                applied=True,
                created_at__gte=lower,
                created_at__lt=upper,
            )
            refunds = RefundRequest.objects.filter(
                payment__booking__resort__in=resorts,
                payment__environment=mode,
                status="succeeded",
                confirmed_at__gte=lower,
                confirmed_at__lt=upper,
            )
        finance = financial_report(
            resorts,
            bookings,
            payments,
            refunds,
            start,
            end,
            mode,
            selected=bool(request.query_params.get("resortId")),
        )
        if resource == "report":
            if finance["resortsTruncated"] or finance["expenseCount"] > 200:
                raise Problem(
                    "Сузьте период или выберите санаторий: выгрузка ограничена 500 санаториями и 200 расходами.",
                    422,
                )
            response = HttpResponse(
                report_xlsx(finance, start, end, mode),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = 'attachment; filename="tynys-finance.xlsx"'
            response["Cache-Control"] = "private, no-store"
            return response
        docs = (
            AccountingDocument.objects.filter(
                booking__resort__in=resorts,
                created_at__gte=lower,
                created_at__lt=upper,
                snapshot__paymentMode__in=[mode, "unpaid"],
            )
            .select_related("booking")
            .order_by("-created_at")
        )
        if resource == "export":
            if bookings.count() > 5000:
                raise Problem("Сократите период: выгрузка ограничена 5000 строк.", 422)
            data = StringIO()
            writer = csv.writer(data)
            writer.writerow(
                [
                    "ID",
                    "Санаторий",
                    "Гость",
                    "Номер",
                    "Заезд",
                    "Выезд",
                    "Стоимость проживания KZT",
                    "Полная стоимость KZT",
                    "Онлайн-оплата по условиям KZT",
                    "Оплата в санатории по условиям KZT",
                    "Отмечено сотрудником в санатории KZT",
                    "Источник",
                    "Статус онлайн-оплаты",
                    "Возвращено KZT",
                ]
            )
            for b in bookings_data(bookings.order_by("-created_at")):
                p = b["payment"] or {}
                row = [
                    b["id"],
                    b["resort"],
                    b["guest"],
                    b["room"],
                    b["start"],
                    b["end"],
                    b["amount"],
                    b["customerTotal"],
                    b["onlineAmount"],
                    b["onsiteAmount"],
                    b["onsitePayment"]["amount"]
                    if b["onsitePayment"]["status"] == "recorded"
                    else 0,
                    p.get("paymentMode", "unpaid"),
                    p.get("status", "unpaid"),
                    p.get("refundedAmount", 0),
                ]
                writer.writerow(
                    [
                        ("'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v)
                        if isinstance(v, str)
                        else v
                        for v in row
                    ]
                )
            response = HttpResponse(
                "\ufeff" + data.getvalue(), content_type="text/csv; charset=utf-8"
            )
            response["Content-Disposition"] = 'attachment; filename="accounting.csv"'
            return response
        if resource != "overview":
            raise Problem("Не найдено.", 404)
        page = serializers.IntegerField(min_value=1, max_value=10000).run_validation(
            request.query_params.get("page", 1)
        )
        return Response(
            {
                "resorts": list(svc.resorts_for(request.user).values("id", "name")),
                "start": str(start),
                "end": str(end),
                "paymentMode": mode,
                "totals": finance["totals"],
                "finance": finance,
                "count": bookings.count(),
                "page": page,
                "bookings": bookings_data(
                    bookings.order_by("-created_at")[(page - 1) * 50 : page * 50]
                ),
                "documents": [svc.document_data(d) for d in docs[:200]],
                "documentCount": docs.count(),
            }
        )

    def post(self, request, resource, pk=None, action=None):
        svc.require_accountant(request.user)
        enforce_limit(request, "accounting-write", ip_limit=60, minutes=5)
        if not isinstance(request.data, dict):
            raise Problem("Передайте JSON-объект.")
        if resource == "expenses":
            return Response(
                void_expense(request, pk) if pk else create_expense(request),
                status=200 if pk else 201,
            )
        if resource == "documents" and pk:
            return Response(svc.change_document(request, pk, action))
        if resource != "documents" or set(request.data) != {"bookingId", "kind"}:
            raise Problem("Передайте bookingId и kind.")
        booking = get_object_or_404(
            Booking.objects.select_related("resort", "room"),
            pk=str(request.data["bookingId"]),
            resort__in=svc.resorts_for(request.user),
        )
        kind = serializers.ChoiceField(choices=svc.KINDS).run_validation(request.data["kind"])
        return Response(
            svc.document_data(svc.prepare_document(booking, kind, request.user)), status=201
        )

    def patch(self, request, resource, pk):
        svc.require_accountant(request.user)
        enforce_limit(request, "accounting-write", ip_limit=60, minutes=5)
        if resource != "company":
            raise Problem("Не найдено.", 404)
        return Response(svc.save_company(request, pk))


def download(doc, kind):
    if kind not in ("pdf", "xlsx"):
        raise Problem("Формат не найден.", 404)
    data = pdf_bytes(doc) if kind == "pdf" else xlsx_bytes(doc)
    content_type = (
        "application/pdf"
        if kind == "pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{doc.number}.{kind}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class GuestDocumentsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk=None, format_kind=None):
        docs = AccountingDocument.objects.filter(
            booking__owner=guest_owner(request), booking__source="website", state="released"
        ).select_related("booking")
        if pk:
            enforce_limit(request, "accounting-download", ip_limit=60, minutes=5)
            return download(get_object_or_404(docs, pk=pk), format_kind)
        booking_id = request.query_params.get("bookingId")
        if booking_id:
            docs = docs.filter(booking_id=booking_id)
        return Response([svc.document_data(d) for d in docs.order_by("-created_at")[:200]])


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class BookingDocumentsView(APIView):
    """Operational read access without access to the accounting workspace."""

    permission_classes = [AllowAny]

    def get(self, request, booking_id, pk=None, format_kind=None):
        require_staff(request.user, roles=("admin", "manager", "accountant"))
        bookings = Booking.objects.all()
        if not admin(request.user) and request.user.role != "accountant":
            bookings = bookings.filter(resort__account=request.user)
        booking = get_object_or_404(bookings, pk=booking_id)
        docs = AccountingDocument.objects.filter(booking=booking).select_related("booking")
        if pk:
            enforce_limit(request, "accounting-download", ip_limit=60, minutes=5)
            return download(get_object_or_404(docs, pk=pk), format_kind)
        return Response([svc.document_data(doc) for doc in docs.order_by("-created_at")[:200]])
