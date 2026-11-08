from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers

from booking.errors import Problem
from booking.models import Booking, Resort

from .models import DemoPayment, DemoRefund, PaymentAttempt, RefundRequest
from .receipts import freeze_receipt
from .settlement import online_amount

PARTIAL_REFUND_PERCENT = 70
POLICY_TEXT = (
    "За 48 часов и более до заезда — возврат 100%; от 24 до 48 часов — 70%; "
    "менее чем за 24 часа — без возврата. Расчёт по времени заезда санатория. "
    "Оплата и возврат демонстрационные, деньги не списываются."
)


def freeze_cancellation_terms(resort, start):
    check_in = getattr(resort, "check_in_time", time(14, 0))
    zone = getattr(resort, "time_zone", "Asia/Almaty")
    checkin_at = datetime.combine(start, check_in, tzinfo=ZoneInfo(zone))
    return {
        "mode": "demo",
        "checkinAt": checkin_at.isoformat(),
        "checkInTime": check_in.strftime("%H:%M"),
        "timeZone": zone,
        "partialRefundPercent": PARTIAL_REFUND_PERCENT,
        "policyText": POLICY_TEXT,
    }


def cancellation_terms(booking):
    frozen = booking.snapshot.get("cancellationPolicy")
    if frozen:
        return frozen
    # Existing bookings predate policy configuration. Keep a stable legacy default.
    return {
        "mode": "demo",
        "checkinAt": datetime.combine(
            booking.stay.lower, time(14), tzinfo=ZoneInfo("Asia/Almaty")
        ).isoformat(),
        "checkInTime": "14:00",
        "timeZone": "Asia/Almaty",
        "partialRefundPercent": PARTIAL_REFUND_PERCENT,
        "policyText": POLICY_TEXT,
    }


def payment_data(payment):
    return {
        "id": payment.id,
        "bookingId": payment.booking_id,
        "status": payment.status,
        "paymentMode": "demo",
        "provider": "kaspi-demo",
        "currency": "KZT",
        "amount": payment.amount,
        "refundedAmount": payment.refunded_amount,
        "createdAt": payment.created_at.isoformat(),
        "receiptUrl": f"/receipts/{payment.id}" if payment.outcome == "success" else None,
    }


def bank_payment_data(payment):
    refund = getattr(payment, "refund", None)
    refunded = refund.amount if refund and refund.status == "succeeded" else 0
    status = "paid" if payment.applied_at else payment.status
    if refunded:
        status = "refunded" if refunded == payment.amount else "partially_refunded"
    return {
        "id": str(payment.pk),
        "bookingId": str(payment.booking_id),
        "status": status,
        "checkoutStatus": payment.status,
        "paymentMode": payment.environment,
        "provider": payment.provider,
        "currency": payment.currency,
        "amount": payment.amount,
        "refundedAmount": refunded,
        "refundStatus": refund.status if refund else None,
        "receiptUrl": None,
        "createdAt": payment.created_at.isoformat(),
    }


def has_paid_booking(booking):
    bank = getattr(booking, "bank_payment", None)
    if bank and bank.applied_at:
        return not RefundRequest.objects.filter(payment=bank).exists()
    return booking.demo_payments.filter(outcome="success", status="paid").exists()


def booking_payment_data(booking):
    bank = getattr(booking, "bank_payment", None)
    if bank:
        return bank_payment_data(bank)
    payments = list(booking.demo_payments.all())
    payment = next((p for p in payments if p.outcome == "success"), None)
    payment = payment or max(payments, key=lambda p: p.created_at, default=None)
    return payment_data(payment) if payment else None


def _require_owner(request, booking):
    from booking.services import guest_owner

    if booking.source != "website" or booking.owner != guest_owner(request):
        raise Problem("Бронирование не найдено.", 404)


class PaymentInput(serializers.Serializer):
    bookingId = serializers.CharField(max_length=64)
    requestId = serializers.UUIDField()
    outcome = serializers.ChoiceField(choices=["success", "failed"])


@transaction.atomic
def _create_demo_payment(request, staff=False):
    from booking.serializers import booking_data
    from booking.services import log_change, require_staff

    if not settings.PAYMENTS_ALLOW_SIMULATOR:
        raise Problem("Симулятор оплаты отключён.", 403)
    inp = PaymentInput(data=request.data)
    inp.is_valid(raise_exception=True)
    data = inp.validated_data
    booking = get_object_or_404(Booking, pk=data["bookingId"])
    if staff:
        require_staff(request.user, booking.resort_id)
        if booking.source != "staff":
            raise Problem("Оплату гостевой брони выполняет сам гость.", 403)
    else:
        _require_owner(request, booking)
    Resort.objects.select_for_update().get(pk=booking.resort_id)
    booking.refresh_from_db()
    if PaymentAttempt.objects.filter(booking=booking).exists():
        raise Problem("Для брони уже создан банковский счёт.", 409)
    previous = DemoPayment.objects.filter(request_key=data["requestId"]).first()
    if previous:
        if previous.booking_id != booking.id or previous.outcome != data["outcome"]:
            raise Problem("Ключ запроса уже использован для другой оплаты.", 409)
        return previous
    if booking.status not in ["pending", "confirmed"]:
        raise Problem("Эта бронь больше не доступна для оплаты.", 409)
    if (
        booking.hold_expires_at
        and booking.status == "pending"
        and timezone.now() >= booking.hold_expires_at
    ):
        raise Problem("Время оплаты истекло. Создайте новую бронь.", 409)
    if timezone.now() >= datetime.fromisoformat(cancellation_terms(booking)["checkinAt"]):
        raise Problem("Время заезда уже наступило. Обратитесь к управляющему.", 409)
    if booking.demo_payments.filter(outcome="success").exists():
        raise Problem("Это бронирование уже оплачено.", 409)
    payment = DemoPayment.objects.create(
        booking=booking,
        request_key=data["requestId"],
        outcome=data["outcome"],
        status="paid" if data["outcome"] == "success" else "failed",
        amount=online_amount(booking),
    )
    if payment.outcome == "success":
        before = booking_data(booking)
        if booking.status == "pending":
            booking.status = "confirmed"
            booking.version += 1
            booking.save(update_fields=["status", "version"])
        payment.receipt = freeze_receipt(payment)
        payment.save(update_fields=["receipt"])
        log_change(
            request.user,
            "bookings",
            booking,
            "payment_confirmed",
            before,
            booking_data(booking),
            booking.resort_id,
            website=not staff,
        )
    log_change(
        request.user,
        "payments",
        payment,
        "demo_payment",
        None,
        payment_data(payment),
        booking.resort_id,
        website=not staff,
    )
    return payment


def create_demo_payment(request, staff=False):
    from booking.holds import expire_resort_holds
    from booking.services import require_staff

    if not settings.PAYMENTS_ALLOW_SIMULATOR:
        raise Problem("Симулятор оплаты отключён.", 403)
    inp = PaymentInput(data=request.data)
    inp.is_valid(raise_exception=True)
    booking = get_object_or_404(Booking, pk=inp.validated_data["bookingId"])
    if staff:
        require_staff(request.user, booking.resort_id)
        if booking.source != "staff":
            raise Problem("Оплату гостевой брони выполняет сам гость.", 403)
    else:
        _require_owner(request, booking)
    # Expiry commits even when the subsequent payment is refused.
    expire_resort_holds(booking.resort_id)
    return _create_demo_payment(request, staff=staff)


def cancellation_preview(booking, *, staff=False, now=None):
    bank = getattr(booking, "bank_payment", None)
    if bank and hasattr(bank, "refund"):
        return {
            **bank.refund.policy,
            "refundStatus": bank.refund.status,
            "finalized": bank.refund.status == "succeeded",
        }
    payment = booking.demo_payments.filter(outcome="success").first()
    if payment:
        previous = DemoRefund.objects.filter(payment=payment).first()
        if previous:
            return {**previous.policy, "finalized": True}
    terms = cancellation_terms(booking)
    checkin_at = datetime.fromisoformat(terms["checkinAt"])
    remaining = (checkin_at - (now or timezone.now())).total_seconds()
    percent = (
        100
        if remaining >= 48 * 3600
        else (terms["partialRefundPercent"] if remaining >= 24 * 3600 else 0)
    )
    amount = bank.amount if bank and bank.applied_at else (payment.amount if payment else 0)
    result = {
        **terms,
        "paidAmount": amount,
        "refundAmount": amount * percent // 100,
        "refundPercent": percent,
        "hoursBeforeCheckin": round(remaining / 3600, 4),
        "actorKind": "provider" if staff else "guest",
    }
    if bank:
        result["mode"] = bank.environment
    return result


def preview_for_request(request, pk):
    from booking.services import guest_owner, require_staff

    booking = get_object_or_404(Booking, pk=pk)
    owns = booking.source == "website" and booking.owner == guest_owner(request)
    if (
        not request.user.is_authenticated
        and not owns
        and request.query_params.get("asStaff") != "true"
    ):
        raise Problem("Бронирование не найдено.", 404)
    staff = request.query_params.get("asStaff") == "true" or not owns
    if staff:
        require_staff(request.user, booking.resort_id)
    else:
        _require_owner(request, booking)
    return cancellation_preview(booking, staff=staff)


@transaction.atomic
def apply_cancellation(booking, user, *, staff=False):
    """Called in booking transition's transaction; same resort lock orders all mutations."""
    from booking.services import log_change

    Resort.objects.select_for_update().get(pk=booking.resort_id)
    from .jobs import retire_booking
    from .refund_services import queue_refund

    retire_booking(booking)
    bank = PaymentAttempt.objects.filter(booking=booking).first()
    if bank and bank.applied_at:
        return queue_refund(bank, cancellation_preview(booking, staff=staff))
    payment = booking.demo_payments.filter(outcome="success").first()
    if payment:
        previous = DemoRefund.objects.filter(payment=payment).first()
        if previous:
            return previous.policy
    preview = cancellation_preview(booking, staff=staff)
    if not payment:
        return preview
    before = payment_data(payment)
    DemoRefund.objects.create(
        payment=payment,
        amount=preview["refundAmount"],
        percent=preview["refundPercent"],
        policy=preview,
        actor_kind=preview["actorKind"],
    )
    payment.refunded_amount = preview["refundAmount"]
    if payment.refunded_amount == payment.amount:
        payment.status = "refunded"
    elif payment.refunded_amount:
        payment.status = "partially_refunded"
    payment.version += 1
    payment.save(update_fields=["refunded_amount", "status", "version"])
    log_change(
        user,
        "payments",
        payment,
        "demo_refund",
        before,
        {**payment_data(payment), "refundPolicy": preview},
        booking.resort_id,
        website=not staff,
    )
    return preview
