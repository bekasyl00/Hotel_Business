"""Authenticated, bounded scheduler entrypoint for a hosted cron service."""

import secrets
import time

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .jobs import run_one, schedule_due
from .payment_services import capabilities


@csrf_exempt
@require_POST
@never_cache
def tick(request):
    key = settings.PAYMENTS_SCHEDULER_SECRET
    supplied = request.headers.get("Authorization", "")
    if len(key) < 32 or not secrets.compare_digest(supplied, "Bearer " + key):
        return JsonResponse({"message": "Unauthorized"}, status=401)
    start = time.monotonic()
    schedule_due()
    count = 0
    while count < 5 and time.monotonic() - start < 45:
        if not run_one():
            break
        count += 1
    return JsonResponse({"processed": count, "bankEnabled": capabilities()["available"]})
