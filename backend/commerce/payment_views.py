import re

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from booking.authentication import bearer_or_csrf_protect
from booking.errors import Problem
from booking.guest_auth import enforce_limit

from . import payment_services as services
from .jobs import enqueue, run_one
from .models import PaymentAttempt
from .provider_config import HalykConfig
from .providers.base import ProviderError


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class PaymentView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk=None, staff=False):
        if pk is None:
            return Response(services.capabilities())
        return Response(services.payment_data(services.for_request(request, pk, staff=staff)))

    def post(self, request, pk=None, staff=False):
        enforce_limit(request, "payment-write", ip_limit=60, minutes=5)
        if pk is None:
            payment = services.create_checkout(request, staff=staff)
        else:
            payment = services.for_request(request, pk, staff=staff)
            enqueue(payment, "verify")
            if getattr(payment, "refund", None) and payment.refund.status == "submitted":
                enqueue(payment, "refund_verify")
        if settings.PAYMENTS_INLINE_CHECKOUT:
            # One durable leased job after the creation transaction commits. Cron
            # recovers interruptions; a browser retry never repeats an uncertain POST.
            run_one(
                payment_id=payment.pk,
                kinds=["create"] if pk is None else ["verify", "refund_verify"],
            )
            payment = services.for_request(request, payment.pk, staff=staff)
        return Response(services.payment_data(payment), status=202)


@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")
class HalykCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            raise Problem("Invalid payload length.", 422) from None
        if length < 0 or length > 16384 or len(request.body) > 16384:
            raise Problem("Payload too large.", 413)
        enforce_limit(request, "halyk-callback", ip_limit=120, minutes=1)
        data = request.data
        if not isinstance(data, dict):
            raise Problem("Invalid callback.", 422)
        invoice = str(
            data.get("invoiceId") or data.get("invoiceID") or data.get("invoice_id") or ""
        )
        # The callback is NOT authenticated payment evidence. It can only coalesce
        # a bounded server lookup; amount/status/signatures in the body are ignored.
        if re.fullmatch(r"[0-9]{6,15}", invoice):
            try:
                config = HalykConfig.from_settings(require_gate=False)
            except ProviderError:
                return JsonResponse({"accepted": True})
            payment = PaymentAttempt.objects.filter(
                invoice_id=invoice,
                environment="sandbox",
                provider="halyk_epay",
                merchant_scope=config.merchant_scope,
            ).first()
            if payment:
                enqueue(payment, "verify")
        return JsonResponse({"accepted": True})
