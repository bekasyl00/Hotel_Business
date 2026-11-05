from django.db import transaction
from django.utils import timezone

from booking.models import Resort

from .models import PaymentEvent, RefundRequest
from .providers.base import ProviderError


def queue_refund(payment, preview):
    from .jobs import enqueue

    refund, created = RefundRequest.objects.get_or_create(
        payment=payment,
        defaults={
            "amount": preview["refundAmount"],
            "percent": preview["refundPercent"],
            "policy": preview,
            "actor_kind": preview["actorKind"],
        },
    )
    if created:
        if refund.amount == 0:
            refund.status, refund.confirmed_at = "succeeded", timezone.now()
        elif payment.provider == "halyk_epay" and refund.amount < 10:
            refund.status, refund.reconciliation_reason = (
                "reconciliation_required",
                "bank_refund_below_minimum",
            )
        else:
            enqueue(payment, "refund")
        refund.save()
    return {
        **refund.policy,
        "refundStatus": refund.status,
        "finalized": refund.status == "succeeded",
    }


def process_refund(payment, provider, *, verify=False):
    from .jobs import enqueue

    refund = RefundRequest.objects.get(payment=payment)
    if refund.status in ("succeeded", "reconciliation_required"):
        return
    charge = payment.events.filter(kind="charge", applied=True).first()
    if not charge:
        raise ProviderError("refund_charge_missing")
    if not verify and not refund.submitted_at:
        if payment.provider == "xpayment":
            verified_charge = provider.lookup_payment(payment.invoice_id)
            if (
                not verified_charge
                or verified_charge.status != "CHARGE"
                or verified_charge.transaction_id != charge.transaction_id
                or verified_charge.invoice_id != payment.invoice_id
                or verified_charge.currency != payment.currency
                or verified_charge.amount != payment.amount
            ):
                raise ProviderError("bank_refund_mismatch")
        with transaction.atomic():
            Resort.objects.select_for_update().get(pk=payment.booking.resort_id)
            refund.refresh_from_db()
            if refund.submitted_at:
                enqueue(payment, "refund_verify")
                return
            refund.submitted_at, refund.status = timezone.now(), "submitted"
            refund.save(update_fields=["submitted_at", "status"])
            enqueue(payment, "refund_verify", delay=10)
        # Mark-before-send: an uncertain call is verified, never blindly repeated.
        provider.request_refund(charge.transaction_id, refund.amount, str(refund.pk))
        return
    evidence = (
        provider.lookup_refund(payment, refund)
        if payment.provider == "xpayment"
        else provider.lookup_payment(payment.invoice_id)
    )
    if not evidence or evidence.status != "REFUND":
        raise ProviderError("bank_refund_unverified", retryable=True)
    if (
        evidence.transaction_id != charge.transaction_id
        or evidence.invoice_id != payment.invoice_id
        or evidence.terminal_id != payment.terminal_id
        or evidence.account_id != payment.account_id
        or evidence.currency != payment.currency
        or evidence.original_amount != payment.amount
        or evidence.refunded_amount != refund.amount
        or evidence.amount != payment.amount - refund.amount
    ):
        raise ProviderError("bank_refund_mismatch")
    with transaction.atomic():
        Resort.objects.select_for_update().get(pk=payment.booking.resort_id)
        refund.refresh_from_db()
        if refund.status == "succeeded":
            return
        PaymentEvent.objects.get_or_create(
            provider=payment.provider,
            environment=payment.environment,
            merchant_scope=payment.merchant_scope,
            transaction_id=charge.transaction_id,
            kind="refund",
            defaults={
                "payment": payment,
                "amount": refund.amount,
                "currency": payment.currency,
                "bank_status": "REFUND",
                "applied": True,
                "occurred_at": evidence.occurred_at,
            },
        )
        refund.status, refund.confirmed_at = "succeeded", timezone.now()
        refund.save(update_fields=["status", "confirmed_at"])
