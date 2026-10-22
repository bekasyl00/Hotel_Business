"""Keep native guest credentials separate from Django staff authentication."""

import re
from dataclasses import dataclass
from functools import wraps

from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import BaseAuthentication

from identity.models import GuestDevice

from .errors import Problem


@dataclass(frozen=True)
class GuestTokenContext:
    device: GuestDevice

    @property
    def account(self):
        return self.device.account


def token_hash(value):
    return salted_hmac("native-guest-token", value, algorithm="sha256").hexdigest()


def invalid_token():
    return Problem("Сессия приложения недействительна. Войдите снова.", 401, "invalid_token")


def bearer_context(request):
    raw_request = getattr(request, "_request", request)
    if hasattr(raw_request, "_guest_bearer_context"):
        return raw_request._guest_bearer_context
    header = getattr(request, "META", {}).get("HTTP_AUTHORIZATION")
    if header is None:
        return None
    parts = header.split()
    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
        or not re.fullmatch(r"tg_a_[A-Za-z0-9_-]{43}", parts[1])
    ):
        raise invalid_token()
    now = timezone.now()
    device = (
        GuestDevice.objects.select_related("account__profile")
        .filter(
            access_hash=token_hash(parts[1]),
            access_expires_at__gt=now,
            expires_at__gt=now,
            revoked_at__isnull=True,
            account__is_active=True,
        )
        .first()
    )
    if not device or device.auth_version != device.account.auth_version:
        raise invalid_token()
    context = GuestTokenContext(device)
    raw_request._guest_bearer_context = context
    return context


class GuestBearerAuthentication(BaseAuthentication):
    def authenticate(self, request):
        context = bearer_context(request)
        # AnonymousUser deliberately preserves the existing staff-only checks.
        return (AnonymousUser(), context) if context else None

    def authenticate_header(self, request):
        return "Bearer"


def bearer_or_csrf_protect(view):
    """Skip cookie CSRF only after authenticating an explicit guest Bearer token."""

    protected = csrf_protect(view)

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            context = bearer_context(request)
        except Problem as exc:
            response = JsonResponse(
                {"message": str(exc.detail), "code": exc.machine_code}, status=exc.status_code
            )
            response["Cache-Control"] = "no-store"
            response["WWW-Authenticate"] = "Bearer"
            return response
        return (view if context else protected)(request, *args, **kwargs)

    return wrapped
