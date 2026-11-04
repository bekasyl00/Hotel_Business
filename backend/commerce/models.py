from django.db import models
from django.db.models import F, Q

from booking.models import Booking, Record


class DemoPayment(Record):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="demo_payments")
    request_key = models.UUIDField(unique=True)
    outcome = models.CharField(
        max_length=10, choices=[("success", "success"), ("failed", "failed")]
    )
    status = models.CharField(
        max_length=24,
        choices=[(s, s) for s in ["paid", "failed", "partially_refunded", "refunded"]],
    )
    amount = models.PositiveIntegerField()
    refunded_amount = models.PositiveIntegerField(default=0)
    receipt = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking"],
                condition=Q(outcome="success"),
                name="one_successful_demo_payment",
            ),
            models.CheckConstraint(
                condition=Q(refunded_amount__lte=F("amount")), name="demo_refund_not_above_paid"
            ),
        ]


class DemoRefund(Record):
    payment = models.OneToOneField(DemoPayment, on_delete=models.PROTECT, related_name="refund")
    amount = models.PositiveIntegerField()
    percent = models.PositiveSmallIntegerField()
    policy = models.JSONField(default=dict)
    actor_kind = models.CharField(
        max_length=16, choices=[("guest", "guest"), ("provider", "provider")]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(percent__lte=100), name="demo_refund_percent")
        ]


class InvoicePool(models.Model):
    """Never recycle the provider's six-digit suffix within a merchant scope."""

    scope = models.CharField(max_length=64, primary_key=True)
    next_value = models.PositiveIntegerField()


class PaymentAttempt(Record):
    # One durable bank checkout per booking, including ambiguous network outcomes.
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="bank_payment")
    provider = models.CharField(max_length=24, default="halyk_epay")
    environment = models.CharField(max_length=16, default="sandbox")
    merchant_scope = models.CharField(max_length=64)
    request_key = models.UUIDField(unique=True)
    fingerprint = models.CharField(max_length=64)
    actor_binding = models.CharField(max_length=64)
    invoice_id = models.CharField(max_length=15)
    shop_id = models.CharField(max_length=64)
    terminal_id = models.CharField(max_length=64)
    account_id = models.CharField(max_length=64)
    amount = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="KZT")
    locale = models.CharField(max_length=2, default="ru")
    recipient_email = models.EmailField(blank=True)
    recipient_phone = models.CharField(max_length=16, blank=True)
    status = models.CharField(
        max_length=32,
        default="creating",
        choices=[
            (s, s)
            for s in [
                "creating",
                "pending",
                "succeeded",
                "failed",
                "expired",
                "reconciliation_required",
            ]
        ],
    )
    invoice_link_id = models.CharField(max_length=64, blank=True)
    checkout_url = models.URLField(max_length=500, blank=True)
    creation_started_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField()
    applied_at = models.DateTimeField(null=True)
    last_verified_at = models.DateTimeField(null=True)
    deactivated_at = models.DateTimeField(null=True)
    reconciliation_reason = models.CharField(max_length=64, blank=True)
    bank_status = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "environment", "merchant_scope", "invoice_id"],
                name="bank_invoice_scope_unique",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="bank_amount_positive"),
            models.CheckConstraint(condition=Q(environment="sandbox"), name="bank_sandbox_only"),
        ]
        indexes = [models.Index(fields=["status", "expires_at"])]


class PaymentEvent(Record):
    """Sanitized, independently verified bank facts; never raw callback payloads."""

    payment = models.ForeignKey(PaymentAttempt, on_delete=models.PROTECT, related_name="events")
    provider = models.CharField(max_length=24)
    environment = models.CharField(max_length=16)
    merchant_scope = models.CharField(max_length=64)
    transaction_id = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=[("charge", "charge"), ("refund", "refund")])
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    applied = models.BooleanField(default=False)
    bank_status = models.CharField(max_length=32)
    occurred_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "environment", "merchant_scope", "transaction_id", "kind"],
                name="bank_event_scope_unique",
            ),
            models.UniqueConstraint(
                fields=["payment"],
                condition=Q(kind="charge", applied=True),
                name="one_applied_bank_charge",
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="bank_event_nonnegative"),
        ]


class RefundRequest(Record):
    payment = models.OneToOneField(PaymentAttempt, on_delete=models.PROTECT, related_name="refund")
    amount = models.PositiveBigIntegerField()
    percent = models.PositiveSmallIntegerField()
    policy = models.JSONField(default=dict)
    actor_kind = models.CharField(max_length=16)
    status = models.CharField(
        max_length=32,
        default="queued",
        choices=[(s, s) for s in ["queued", "submitted", "succeeded", "reconciliation_required"]],
    )
    submitted_at = models.DateTimeField(null=True)
    confirmed_at = models.DateTimeField(null=True)
    reconciliation_reason = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(percent__lte=100), name="bank_refund_percent"),
        ]


class PaymentJob(Record):
    payment = models.ForeignKey(PaymentAttempt, on_delete=models.PROTECT, related_name="jobs")
    kind = models.CharField(
        max_length=24,
        choices=[
            (s, s)
            for s in [
                "create",
                "verify",
                "deactivate",
                "refund",
                "refund_verify",
            ]
        ],
    )
    state = models.CharField(
        max_length=12,
        default="pending",
        choices=[
            (s, s)
            for s in [
                "pending",
                "running",
                "done",
                "dead",
            ]
        ],
    )
    available_at = models.DateTimeField()
    lease_until = models.DateTimeField(null=True)
    lease_token = models.UUIDField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    requested_again = models.BooleanField(default=False)
    last_error = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["payment", "kind"], name="one_bank_job_kind")
        ]
        indexes = [models.Index(fields=["state", "available_at"])]
