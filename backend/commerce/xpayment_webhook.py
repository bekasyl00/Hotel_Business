"""Signed notifications only schedule an authenticated API lookup; never money facts."""

import hashlib
import hmac
import json
import re
from uuid import UUID

from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from booking.errors import Problem
from booking.guest_auth import enforce_limit
from booking.models import Resort

from .jobs import enqueue
from .models import PaymentAttempt, WebhookDelivery
from .provider_config import XPaymentConfig
from .providers.base import ProviderError

EVENTS = {
    "payment.completed",
    "payment.expired",
    "payment.cancelled",
    "payment.failed",
    "payment.refunded",
    "payment.refund_failed",
}


def canonical_uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")
class XPaymentCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            raise Problem("Invalid payload length.", 422) from None
        if length < 0 or length > 16384 or len(request.body) > 16384:
            raise Problem("Payload too large.", 413)
        enforce_limit(request, "xpayment-callback", ip_limit=120, minutes=1)
        try:
            config = XPaymentConfig.from_settings(require_gate=False)
        except ProviderError:
            raise Problem("Webhook not configured.", 503) from None
        signature = request.headers.get("X-xPayment-Signature", "")
        expected = hmac.new(
            config.webhook_secret.encode(), request.body, hashlib.sha256
        ).hexdigest()
        if not re.fullmatch(r"[a-f0-9]{64}", signature) or not hmac.compare_digest(
            signature, expected
        ):
            raise Problem("Invalid signature.", 401)
        try:
            data = json.loads(request.body)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise Problem("Invalid payload.", 422) from None
        if (
            not isinstance(data, dict)
            or data.get("source") != "xpayment"
            or data.get("event_version") != "1"
            or not isinstance(data.get("event"), str)
            or data["event"] not in EVENTS
            or not canonical_uuid(data.get("payment_id"))
            or not canonical_uuid(data.get("delivery_id"))
        ):
            raise Problem("Invalid event.", 422)
        if data.get("environment", "production") != config.environment:
            raise Problem("Invalid payment environment.", 422)
        payments = PaymentAttempt.objects.filter(
            provider="xpayment",
            environment=config.environment,
            merchant_scope=config.merchant_scope,
        )
        order = data.get("merchant_order_id")
        if order:
            if not canonical_uuid(order):
                raise Problem("Invalid order.", 422)
            payment = payments.filter(invoice_id=order).first()
        else:
            payment = payments.filter(invoice_link_id=data["payment_id"]).first()
        if not payment:
            return JsonResponse({"accepted": True})
        with transaction.atomic():
            Resort.objects.select_for_update().get(pk=payment.booking.resort_id)
            payment.refresh_from_db()
            if payment.invoice_link_id and payment.invoice_link_id != data["payment_id"]:
                raise Problem("Invalid payment reference.", 422)
            _, created = WebhookDelivery.objects.get_or_create(
                merchant_scope=config.merchant_scope,
                delivery_id=data["delivery_id"],
                defaults={"payment": payment, "event": data["event"]},
            )
            if created:
                enqueue(payment, "verify")
                if data["event"] in ("payment.refunded", "payment.refund_failed") and hasattr(
                    payment, "refund"
                ):
                    enqueue(payment, "refund_verify")
        return JsonResponse({"accepted": True})
