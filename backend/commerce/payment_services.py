import hashlib
import json
from datetime import datetime
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers

from booking.errors import Problem
from booking.models import Audit, Booking, Resort
from booking.services import guest_owner, require_staff

from .models import InvoicePool, PaymentAttempt, PaymentEvent
from .provider_registry import configuration, environment_for
from .providers.base import ProviderError
from .services import cancellation_terms
from .settlement import online_amount


def capabilities():
    provider = settings.PAYMENT_PROVIDER
    if provider == "simulator":
        return {
            "provider": provider,
            "environment": "demo",
            "available": settings.PAYMENTS_ALLOW_SIMULATOR,
        }
    environment = environment_for(provider)
    production_scope = (
        {"productionResortIds": settings.XPAYMENT_PRODUCTION_RESORT_IDS}
        if provider == "xpayment" and environment == "production"
        else {}
    )
    try:
        configuration()
        if production_scope and not production_scope["productionResortIds"]:
            raise ProviderError("xpayment_production_resorts_missing")
        return {
            "provider": provider,
            "environment": environment,
            "available": True,
            **production_scope,
        }
    except ProviderError as exc:
        return {
            "provider": provider,
            "environment": environment,
            "available": False,
            "reason": exc.code,
            **production_scope,
        }


def authorize(request, booking, *, staff=False):
    if staff:
        require_staff(request.user, booking.resort_id)
        if booking.source != "staff":
            raise Problem("Оплату гостевой брони выполняет сам гость.", 403)
        return hashlib.sha256(("staff:" + str(request.user.pk)).encode()).hexdigest()
    if booking.source != "website" or booking.owner != guest_owner(request):
        raise Problem("Бронирование не найдено.", 404)
    return hashlib.sha256(("guest:" + booking.owner).encode()).hexdigest()


def for_request(request, pk, *, staff=False):
    payment = get_object_or_404(PaymentAttempt.objects.select_related("booking"), pk=pk)
    authorize(request, payment.booking, staff=staff)
    return payment


def payment_data(payment):
    refund = getattr(payment, "refund", None)
    available = (
        payment.status in ("pending", "failed")
        and payment.checkout_url
        and payment.booking.status == "pending"
        and timezone.now() < payment.expires_at
        and not payment.deactivated_at
    )
    return {
        "id": str(payment.pk),
        "bookingId": str(payment.booking_id),
        "bookingStatus": payment.booking.status,
        "provider": payment.provider,
        "environment": payment.environment,
        "status": payment.status,
        "amount": payment.amount,
        "currency": payment.currency,
        "checkoutUrl": payment.checkout_url if available else None,
        "expiresAt": payment.expires_at.isoformat(),
        "lastVerifiedAt": payment.last_verified_at.isoformat()
        if payment.last_verified_at
        else None,
        "refundStatus": refund.status if refund else None,
        "refundedAmount": refund.amount if refund and refund.status == "succeeded" else 0,
        "reconciliationReason": payment.reconciliation_reason or None,
        "receiptUrl": None,
    }


class CheckoutInput(serializers.Serializer):
    bookingId = serializers.CharField(max_length=64)
    requestKey = serializers.UUIDField()
    locale = serializers.ChoiceField(choices=["ru", "kk", "en"])

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["Неизвестные поля платёжного запроса."]}
            )
        return super().to_internal_value(data)


def create_checkout(request, *, staff=False):
    from booking.holds import expire_resort_holds

    from .jobs import enqueue

    inp = CheckoutInput(data=request.data)
    inp.is_valid(raise_exception=True)
    data = inp.validated_data
    booking = get_object_or_404(Booking, pk=data["bookingId"])
    binding = authorize(request, booking, staff=staff)
    expire_resort_holds(booking.resort_id)
    fingerprint = hashlib.sha256(
        json.dumps({"booking": str(booking.pk), "actor": binding}, sort_keys=True).encode()
    ).hexdigest()
    with transaction.atomic():
        Resort.objects.select_for_update().get(pk=booking.resort_id)
        booking.refresh_from_db()
        previous = PaymentAttempt.objects.filter(request_key=data["requestKey"]).first()
        if previous and (previous.booking_id != booking.pk or previous.fingerprint != fingerprint):
            raise Problem("Ключ запроса уже использован.", 409)
        previous = previous or PaymentAttempt.objects.filter(booking=booking).first()
        if previous:
            if previous.actor_binding != binding:
                raise Problem("Платёж уже создан другим сотрудником.", 409)
            return previous
        if (
            settings.PAYMENT_PROVIDER == "xpayment"
            and environment_for("xpayment") == "production"
            and str(booking.resort_id) not in settings.XPAYMENT_PRODUCTION_RESORT_IDS
        ):
            raise Problem(
                "Оплата этого санатория пока не подключена.",
                409,
                "payment_resort_not_enabled",
            )
        try:
            config = configuration()
        except ProviderError as exc:
            raise Problem("Банковская оплата временно недоступна.", 503, exc.code) from None
        now = timezone.now()
        if (
            booking.status != "pending"
            or not booking.hold_expires_at
            or booking.hold_expires_at <= now
            or now >= datetime.fromisoformat(cancellation_terms(booking)["checkinAt"])
            or booking.demo_payments.filter(outcome="success").exists()
        ):
            raise Problem("Бронь недоступна для оплаты.", 409)
        amount = online_amount(booking)
        if type(amount) is not int or amount <= 0:
            raise Problem("Некорректная сохранённая сумма брони.", 409)
        scope = config.merchant_scope
        if settings.PAYMENT_PROVIDER == "halyk_epay":
            InvoicePool.objects.get_or_create(
                scope=scope, defaults={"next_value": config.invoice_start}
            )
            pool = InvoicePool.objects.select_for_update().get(pk=scope)
            if pool.next_value > config.invoice_end:
                raise Problem("Пул тестовых счетов исчерпан.", 503)
            invoice = config.invoice_prefix + str(pool.next_value)
            pool.next_value += 1
            pool.save(update_fields=["next_value"])
            identity = dict(
                shop_id=config.shop_id,
                terminal_id=config.terminal_id,
                account_id="tynys-" + uuid4().hex,
                recipient_email="checkout@example.invalid",
                recipient_phone="+70000000000",
            )
        else:
            invoice = str(uuid4())
            # These are Halyk-only references; XPayment binds to merchant_scope and order UUID.
            identity = dict(shop_id="", terminal_id="", account_id="")
        payment = PaymentAttempt.objects.create(
            booking=booking,
            provider=settings.PAYMENT_PROVIDER,
            environment=environment_for(settings.PAYMENT_PROVIDER),
            **identity,
            request_key=data["requestKey"],
            fingerprint=fingerprint,
            actor_binding=binding,
            merchant_scope=scope,
            invoice_id=invoice,
            amount=amount,
            locale=data["locale"],
            expires_at=booking.hold_expires_at,
        )
        enqueue(payment, "create")
        return payment


def reconcile_reason(payment, reason):
    payment.status = "reconciliation_required"
    payment.reconciliation_reason = reason
    payment.save(update_fields=["status", "reconciliation_reason", "updated_at"])


@transaction.atomic
def apply_transaction(payment_id, evidence):
    from booking.holds import active_inventory, expire_locked_holds

    payment = PaymentAttempt.objects.select_related("booking").get(pk=payment_id)
    booking = payment.booking
    Resort.objects.select_for_update().get(pk=booking.resort_id)
    expire_locked_holds(booking.resort_id)
    payment.refresh_from_db()
    booking.refresh_from_db()
    payment.last_verified_at = timezone.now()
    payment.save(update_fields=["last_verified_at"])
    if evidence is None:
        return
    # Transaction lookup returns the account reference even when invoice lookup
    # returns an empty account_id. Require the frozen reference on financial evidence.
    if (
        evidence.invoice_id != payment.invoice_id
        or evidence.terminal_id != payment.terminal_id
        or evidence.currency != payment.currency
        or evidence.account_id != payment.account_id
        or (payment.provider == "xpayment" and evidence.transaction_id != payment.invoice_link_id)
    ):
        reconcile_reason(payment, "bank_identity_mismatch")
        return
    payment.bank_status = evidence.status
    payment.save(update_fields=["bank_status"])
    if evidence.status != "CHARGE":
        if evidence.status == "REFUND" and not payment.applied_at:
            reconcile_reason(payment, "refund_without_local_charge")
        elif (
            not payment.applied_at
            and evidence.status
            in ("FAILED", "REJECT", "CANCEL", "CANCEL_OLD", "CANCELLED", "EXPIRED")
            and payment.status not in ("expired", "reconciliation_required")
        ):
            payment.status = "failed"
            payment.save(update_fields=["status"])
        return
    event, created = PaymentEvent.objects.get_or_create(
        provider=payment.provider,
        environment=payment.environment,
        merchant_scope=payment.merchant_scope,
        transaction_id=evidence.transaction_id,
        kind="charge",
        defaults={
            "payment": payment,
            "amount": evidence.amount,
            "currency": evidence.currency,
            "bank_status": evidence.status,
            "occurred_at": evidence.occurred_at,
        },
    )
    if event.payment_id != payment.pk:
        reconcile_reason(payment, "bank_transaction_collision")
        return
    if event.applied:
        return
    if not created:
        return  # Financial exceptions are never silently reapplied by a later poll.
    if evidence.amount != payment.amount:
        reconcile_reason(payment, "bank_amount_mismatch")
        return
    if payment.applied_at or booking.demo_payments.filter(outcome="success").exists():
        reconcile_reason(payment, "additional_charge")
        return
    if payment.status == "reconciliation_required":
        return  # A different charge cannot clear an unresolved financial exception.
    if (
        booking.status != "pending"
        or timezone.now() >= payment.expires_at
        or timezone.now() >= datetime.fromisoformat(cancellation_terms(booking)["checkinAt"])
    ):
        reconcile_reason(payment, "late_charge")
        return
    if (
        Booking.objects.filter(active_inventory(), room=booking.room, stay__overlap=booking.stay)
        .exclude(pk=booking.pk)
        .exists()
    ):
        reconcile_reason(payment, "inventory_conflict")
        return
    before = booking.status
    booking.status = "confirmed"
    booking.version += 1
    booking.save(update_fields=["status", "version"])
    event.applied = True
    event.save(update_fields=["applied"])
    payment.status = "succeeded"
    payment.applied_at = timezone.now()
    payment.reconciliation_reason = ""
    payment.save(update_fields=["status", "applied_at", "reconciliation_reason", "updated_at"])
    Audit.objects.create(
        actor=f"{payment.provider} · серверная сверка",
        resort_id=booking.resort_id,
        entity="bookings",
        entity_id=booking.pk,
        action="payment_confirmed",
        label="Verified payment",
        before={"status": before},
        after={
            "status": "confirmed",
            "paymentId": str(payment.pk),
            "environment": payment.environment,
        },
    )


def checkout_matches(payment, checkout):
    return (
        checkout.invoice_id == payment.invoice_id
        and checkout.shop_id == payment.shop_id
        and checkout.terminal_id == payment.terminal_id
        and checkout.account_id in ("", payment.account_id)
        and checkout.amount == payment.amount
        and checkout.currency == payment.currency
        and (not payment.invoice_link_id or payment.invoice_link_id == checkout.link_id)
    )
