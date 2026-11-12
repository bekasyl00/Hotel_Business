"""Authenticated, bounded scheduler entrypoint for a hosted cron service."""

import secrets
import time

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from booking.push import send_due_pushes

from .jobs import run_one, schedule_due
from .operations import finish_heartbeat, start_heartbeat
from .payment_services import capabilities


@csrf_exempt
@require_POST
@never_cache
def tick(request):
    key = settings.PAYMENTS_SCHEDULER_SECRET
    supplied = request.headers.get("Authorization", "")
    if (
        len(key) < 32
        or len(supplied) > 512
        or not secrets.compare_digest(supplied.encode("utf-8"), ("Bearer " + key).encode("utf-8"))
    ):
        return JsonResponse({"message": "Unauthorized"}, status=401)
    start = time.monotonic()
    token = start_heartbeat("payment_scheduler")
    count = 0
    push_count = 0
    try:
        schedule_due()
        while count < 5 and time.monotonic() - start < 45:
            if not run_one():
                break
            count += 1
        push_count = send_due_pushes(limit=20, deadline=start + 45)
    except Exception:
        finish_heartbeat(
            "payment_scheduler",
            token,
            succeeded=False,
            duration=time.monotonic() - start,
            processed=count + push_count,
        )
        raise
    finish_heartbeat(
        "payment_scheduler",
        token,
        succeeded=True,
        duration=time.monotonic() - start,
        processed=count + push_count,
    )
    return JsonResponse(
        {
            "processed": count,
            "pushProcessed": push_count,
            "bankEnabled": capabilities()["available"],
        }
    )
