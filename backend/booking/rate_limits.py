"""Small shared fixed-window quotas; PostgreSQL, not a per-worker cache, is authoritative."""

import math
from datetime import timedelta
from ipaddress import ip_address

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .errors import Problem
from .models import LoginAttempt


class RateLimited(Problem):
    def __init__(self, wait):
        # DRF's exception handler turns this into the standard Retry-After header.
        self.wait = max(1, math.ceil(wait))
        super().__init__("Слишком много попыток. Повторите позже.", 429, "rate_limited")


def consume_limits(keys, *, minutes=15):
    """Consume every applicable quota, then raise *after* the counter transaction commits.

    Call before domain transactions so failed writes still consume their quota.
    Sorting all keys gives concurrent requests the same row-lock order. Keys are
    already digests, never raw IP addresses, phone numbers or account identifiers.
    """
    now = timezone.now()
    window = timedelta(minutes=minutes)
    wait = 0
    with transaction.atomic():
        for key, limit in sorted(keys):
            row, _ = LoginAttempt.objects.select_for_update().get_or_create(
                key=key, defaults={"since": now}
            )
            if row.since <= now - window:
                row.count, row.since = 0, now
            if row.count >= limit:
                wait = max(wait, (row.since + window - now).total_seconds())
            else:
                row.count += 1
            row.save(update_fields=["count", "since"])
    if wait:
        raise RateLimited(wait)


def quota_key(value):
    # Preserve existing guest counters through rollout; these are server-keyed hashes.
    return salted_hmac("guest-auth", value, algorithm="sha256").hexdigest()


def client_ip(request):
    """Trust Vercel's overwritten header only inside its server runtime.

    https://vercel.com/docs/headers/request-headers#x-vercel-forwarded-for
    A self-hosted deployment must configure its own trusted proxy before using
    any forwarded value. Generic X-Forwarded-For/X-Real-IP are never consulted.
    """
    if getattr(settings, "VERCEL_RUNTIME", False):
        value = request.META.get("HTTP_X_VERCEL_FORWARDED_FOR", "")
        if isinstance(value, str) and value.isascii() and len(value) <= 45 and "%" not in value:
            try:
                return str(ip_address(value))
            except ValueError:
                pass
    return request.META.get("REMOTE_ADDR", "")


def enforce_limit(
    request, prefix, phone=None, phone_limit=10, ip_limit=30, minutes=15,
    *, subject=None, subject_limit=30,
):
    keys = [(quota_key(prefix + ":ip:" + client_ip(request)), ip_limit)]
    if phone:
        keys.append((quota_key(prefix + ":phone:" + phone), phone_limit))
    if subject:
        keys.append((quota_key(prefix + ":subject:" + subject), subject_limit))
    consume_limits(keys, minutes=minutes)


def request_subject(request, *, staff=False):
    """Only authenticated identities count as independent subjects; no client IDs."""
    if staff:
        return "staff:" + str(request.user.pk) if request.user.is_authenticated else None
    from .guest_auth import current_account

    account = current_account(request)
    return "guest:" + str(account.pk) if account else None


def prune_limits(*, days=7, limit=1000, delete=False):
    """Bounded maintenance, never on a request path; active locks are skipped."""
    if not 7 <= days <= 365 or not 1 <= limit <= 5000:
        raise ValueError("Use days between 7 and 365, and limit between 1 and 5000.")
    cutoff = timezone.now() - timedelta(days=days)
    with transaction.atomic():
        keys = list(
            LoginAttempt.objects.filter(since__lt=cutoff)
            .select_for_update(skip_locked=True)
            .order_by("since", "pk")
            .values_list("pk", flat=True)[:limit]
        )
        if delete:
            LoginAttempt.objects.filter(pk__in=keys).delete()
    return len(keys)
