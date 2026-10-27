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
