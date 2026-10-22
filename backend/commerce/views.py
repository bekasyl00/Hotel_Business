from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .receipts import receipt_for_request, receipt_pdf


@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class DemoPaymentView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        return Response(services.payment_data(services.create_demo_payment(request)))


@method_decorator(never_cache, name="dispatch")
class CancellationPreviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        return Response(services.preview_for_request(request, pk))


@method_decorator(never_cache, name="dispatch")
class ReceiptView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk, pdf=False):
        payload = receipt_for_request(request, pk)
        if not pdf:
            return Response(payload)
        response = HttpResponse(receipt_pdf(payload), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{payload["receipt"]["number"]}.pdf"'
        )
        return response
