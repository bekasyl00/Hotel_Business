"""Durable, leased PostgreSQL jobs. HTTP is always outside inventory transactions."""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from booking.models import Booking, Resort

from .models import PaymentAttempt, PaymentJob
from .payment_services import apply_transaction, checkout_matches, reconcile_reason
from .provider_registry import processable_jobs, provider_for
from .providers.base import ProviderError


@transaction.atomic
def enqueue(payment, kind, *, delay=0):
    job, created = PaymentJob.objects.get_or_create(
        payment=payment,
        kind=kind,
        defaults={"available_at": timezone.now() + timedelta(seconds=delay)},
    )
    if not created:
        job = PaymentJob.objects.select_for_update().get(pk=job.pk)
        if job.state == "running":
            job.requested_again = True
        elif job.state == "done":
            job.state = "pending"
            job.available_at = timezone.now() + timedelta(seconds=delay)
            job.attempts = 0
        # Pending backoff and dead-letter states cannot be reset by callback floods.
        job.save()
    return job


def retire_booking(booking):
    payment = PaymentAttempt.objects.filter(booking=booking).first()
    if not payment:
        return
    if not payment.applied_at and payment.status != "reconciliation_required":
        payment.status = "expired"
        payment.save(update_fields=["status"])
    enqueue(payment, "deactivate")
    enqueue(payment, "verify")


@transaction.atomic
def claim(*, payment_id=None, allowed=None):
    now = timezone.now()
    query = PaymentJob.objects.filter(
        Q(state="pending", available_at__lte=now) | Q(state="running", lease_until__lt=now)
    )
    if allowed is not None:
        query = query.filter(allowed)
    if payment_id:
        query = query.filter(payment_id=payment_id)
    job = (
        query.select_for_update(of=("self",), skip_locked=True)
        .order_by("available_at", "id")
        .first()
    )
    if not job:
        return None
    job.state, job.lease_token = "running", uuid4()
    job.lease_until = now + timedelta(seconds=120)
    job.attempts += 1
    job.requested_again = False
    job.save()
    return job


@transaction.atomic
def finish(job, error=None):
    current = PaymentJob.objects.select_for_update().get(pk=job.pk)
    if current.lease_token != job.lease_token:
        return
    retry = error is not None or current.requested_again
    current.state = "pending" if retry else "done"
    if error and (current.attempts >= 10 or not (error.retryable or error.ambiguous)):
        current.state = "dead"
    current.last_error = error.code if error else ""
    current.available_at = timezone.now() + timedelta(
        seconds=min(2 ** min(current.attempts, 8), 300)
    )
    current.lease_until = None
    current.lease_token = None
    current.save()


def create_bank_link(payment, provider):
    checkout = provider.find_checkout(payment.invoice_id)
    if checkout is None:
        with transaction.atomic():
            Resort.objects.select_for_update().get(pk=payment.booking.resort_id)
            payment.refresh_from_db()
            payment.booking.refresh_from_db()
            if payment.creation_started_at:
                # Never repeat an ambiguous POST even when the bank's read replica is late.
                raise ProviderError("bank_creation_uncertain", retryable=True)
            if payment.booking.status != "pending" or timezone.now() >= payment.expires_at:
                return
            payment.creation_started_at = timezone.now()
            payment.save(update_fields=["creation_started_at"])
        try:
            checkout = provider.create_checkout(payment)
        except ProviderError:
            checkout = provider.find_checkout(payment.invoice_id)
            if checkout is None:
                raise ProviderError("bank_creation_uncertain", retryable=True) from None
    if not checkout_matches(payment, checkout):
        raise ProviderError("bank_invoice_collision")
    with transaction.atomic():
        Resort.objects.select_for_update().get(pk=payment.booking.resort_id)
        payment.refresh_from_db()
        payment.booking.refresh_from_db()
        if not checkout_matches(payment, checkout):
            raise ProviderError("bank_invoice_collision")
        payment.invoice_link_id = checkout.link_id
        payment.checkout_url = checkout.url or payment.checkout_url
        if checkout.expires_at:
            payment.expires_at = min(payment.expires_at, checkout.expires_at)
            payment.booking.hold_expires_at = min(
                payment.booking.hold_expires_at, payment.expires_at
            )
            payment.booking.save(update_fields=["hold_expires_at"])
        if not payment.applied_at and payment.status not in ("expired", "reconciliation_required"):
            payment.status = "pending"
        payment.save(
            update_fields=["invoice_link_id", "checkout_url", "status", "expires_at", "updated_at"]
        )
        if payment.booking.status != "pending" or timezone.now() >= payment.expires_at:
            enqueue(payment, "deactivate")
        enqueue(payment, "verify")


def verify_bank_payment(payment, provider):
    checkout = provider.find_checkout(payment.invoice_id)
    if checkout is not None and not checkout_matches(payment, checkout):
        raise ProviderError("bank_invoice_collision")
    if checkout is None:
        raise ProviderError("bank_invoice_not_found", retryable=True)
    if not payment.invoice_link_id:
        with transaction.atomic():
            Resort.objects.select_for_update().get(pk=payment.booking.resort_id)
            payment.refresh_from_db()
            if not checkout_matches(payment, checkout):
                raise ProviderError("bank_invoice_collision")
            payment.invoice_link_id = checkout.link_id
            payment.save(update_fields=["invoice_link_id"])
    evidence = provider.lookup_payment(payment.invoice_id)
    apply_transaction(payment.pk, evidence)


def deactivate_bank_link(payment, provider):
    checkout = provider.find_checkout(payment.invoice_id)
    if checkout is None:
        # A concurrent create request may still complete; defer until it is settled.
        create_job = payment.jobs.filter(kind="create").first()
        if payment.creation_started_at and create_job and create_job.state not in ("done", "dead"):
            raise ProviderError("bank_creation_uncertain", retryable=True)
        return
    if not checkout_matches(payment, checkout):
        raise ProviderError("bank_invoice_collision")
    if checkout.status in ("ACTIVE",):
        provider.deactivate_checkout(checkout.link_id)
        checkout = provider.find_checkout(payment.invoice_id)
        if not checkout or checkout.status == "ACTIVE":
            raise ProviderError("bank_deactivation_unverified", retryable=True)
    if checkout.status in ("ANNULLED", "CANCELLED", "EXPIRED", "FAILED"):
        PaymentAttempt.objects.filter(pk=payment.pk).update(deactivated_at=timezone.now())
    elif checkout.status not in ("CHARGED", "CHARGE", "REFUND"):
        raise ProviderError("bank_deactivation_unverified", retryable=True)
    enqueue(payment, "verify")


def execute(job, provider):
    payment = PaymentAttempt.objects.select_related("booking").get(pk=job.payment_id)
    if job.kind == "create":
        create_bank_link(payment, provider)
    elif job.kind == "verify":
        verify_bank_payment(payment, provider)
    elif job.kind == "deactivate":
        deactivate_bank_link(payment, provider)
    else:
        from .refund_services import process_refund

        process_refund(payment, provider, verify=job.kind == "refund_verify")


def run_one(*, provider=None, payment_id=None):
    job = claim(payment_id=payment_id, allowed=None if provider else processable_jobs())
    if not job:
        return False
    error = None
    try:
        payment = PaymentAttempt.objects.get(pk=job.payment_id)
        provider = provider or provider_for(
            payment, creating=job.kind == "create" and not payment.creation_started_at
        )
        execute(job, provider)
    except ProviderError as exc:
        error = exc
        if job.attempts >= 10 or not (exc.retryable or exc.ambiguous):
            with transaction.atomic():
                payment = PaymentAttempt.objects.select_related("booking").get(pk=job.payment_id)
                Resort.objects.select_for_update().get(pk=payment.booking.resort_id)
                payment.refresh_from_db()
                reconcile_reason(payment, exc.code)
                if job.kind in ("refund", "refund_verify"):
                    from .models import RefundRequest

                    RefundRequest.objects.filter(payment=payment).exclude(
                        status="succeeded"
                    ).update(status="reconciliation_required", reconciliation_reason=exc.code)
    except Exception:
        # No bank payloads, contact details, tokens or database params in error logs.
        error = ProviderError("payment_worker_error", retryable=True)
    finish(job, error)
    return True


def schedule_due():
    from booking.holds import expire_resort_holds

    now = timezone.now()
    resort_ids = (
        Booking.objects.filter(status="pending", hold_expires_at__lte=now)
        .values_list("resort_id", flat=True)
        .distinct()[:100]
    )
    for resort_id in resort_ids:
        expire_resort_holds(resort_id)
    candidates = PaymentAttempt.objects.filter(
        Q(last_verified_at__isnull=True) | Q(last_verified_at__lt=now - timedelta(minutes=2))
    )
    # Continue checking retired links for late charges for 48h after creation.
    candidates = candidates.filter(
        Q(status__in=["creating", "pending", "failed"])
        | Q(created_at__gt=now - timedelta(days=2), applied_at__isnull=True)
    )
    for payment in candidates.order_by("last_verified_at", "id")[:100]:
        enqueue(payment, "verify")
    from .models import RefundRequest

    for refund in RefundRequest.objects.filter(status="submitted").select_related("payment")[:100]:
        enqueue(refund.payment, "refund_verify")
