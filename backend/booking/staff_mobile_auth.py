"""Native staff credentials; separate models, endpoints and token namespace."""

import re
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from identity.models import StaffDevice, StaffRefreshToken

from .authentication import (
    StaffBearerAuthentication,
    invalid_token,
    staff_context,
    staff_credential_version,
    token_hash,
)
from .errors import Problem
from .guest_auth import enforce_limit, payload
from .models import Audit, User
from .serializers import account_data
from .services import authenticate_staff_credentials, require_staff

ACCESS_TTL = timedelta(minutes=15)
FAMILY_TTL = timedelta(hours=12)


def audit(user, action):
    Audit.objects.create(
        actor=user.name or user.username,
        resort_id=user.resort_id,
        entity="staff_account",
        entity_id=str(user.pk),
        action=action,
        label="Сессия сотрудника",
        before=None,
        after=None,
    )


def tokens(device, now):
    access, refresh = "ts_a_" + secrets.token_urlsafe(32), "ts_r_" + secrets.token_urlsafe(32)
    device.access_hash = token_hash(access)
    device.access_expires_at = min(now + ACCESS_TTL, device.expires_at)
    device.last_used_at = now
    device.save()
    StaffRefreshToken.objects.create(token_hash=token_hash(refresh), device=device)
    return {
        "tokenType": "Bearer",
        "accessToken": access,
        "refreshToken": refresh,
        "expiresIn": int((device.access_expires_at - now).total_seconds()),
        "refreshExpiresAt": device.expires_at.isoformat(),
        "deviceId": str(device.pk),
        "user": account_data(device.user),
    }


def login(request):
    data = payload(request, ["email", "password", "deviceName"])
    name = data["deviceName"]
    if (
        not isinstance(data["email"], str)
        or not isinstance(name, str)
        or not 1 <= len(name.strip()) <= 80
    ):
        raise Problem("Некорректные данные входа.", 422, "invalid_request")
    # Web and native use the same database-backed failed-login budget.
    user = authenticate_staff_credentials(request)
    credential_version = staff_credential_version(user)
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if not user.is_active or credential_version != staff_credential_version(user):
            raise invalid_token()
        require_staff(user)
        now = timezone.now()
        device = StaffDevice(
            user=user,
            name=name.strip(),
            credential_version=credential_version,
            expires_at=now + FAMILY_TTL,
        )
        result = tokens(device, now)
        audit(user, "native_staff_login")
    return result


def refresh(request):
    value = payload(request, ["refreshToken"])["refreshToken"]
    if not isinstance(value, str) or not re.fullmatch(r"ts_r_[A-Za-z0-9_-]{43}", value):
        raise invalid_token()
    enforce_limit(request, "staff-refresh", ip_limit=120)
    saved = (
        StaffRefreshToken.objects.select_related("device")
        .filter(token_hash=token_hash(value))
        .first()
    )
    if not saved:
        raise invalid_token()
    error = None
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=saved.device.user_id)
        device = StaffDevice.objects.select_for_update().get(pk=saved.device_id)
        saved = StaffRefreshToken.objects.select_for_update().get(pk=saved.pk)
        now = timezone.now()
        if (
            device.revoked_at
            or device.expires_at <= now
            or not user.is_active
            or device.credential_version != staff_credential_version(user)
            or saved.consumed_at
        ):
            if not device.revoked_at:
                device.revoked_at = now
                device.save(update_fields=["revoked_at"])
                audit(user, "native_staff_revoke")
            error = invalid_token()
        else:
            require_staff(user)
            saved.consumed_at = now
            saved.save(update_fields=["consumed_at"])
            device.user = user
            result = tokens(device, now)
    if error:
        raise error  # Keep replay revocation committed.
    return result


def require_context(request):
    context = staff_context(request)
    if not context:
        raise invalid_token()
    return context


@transaction.atomic
def revoke(context, pk):
    user = User.objects.select_for_update().get(pk=context.user.pk)
    device = StaffDevice.objects.select_for_update().filter(pk=pk, user=user).first()
    if not device:
        raise Problem("Не найдено.", 404, "not_found")
    if not device.revoked_at:
        device.revoked_at = timezone.now()
        device.save(update_fields=["revoked_at"])
        audit(user, "native_staff_logout")


@method_decorator(never_cache, name="dispatch")
class StaffMobileAuthView(APIView):
    authentication_classes = [StaffBearerAuthentication]
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request, action):
        if action == "login":
            return Response(login(request))
        if action == "refresh":
            return Response(refresh(request))
        if action == "logout":
            payload(request, [])
            context = require_context(request)
            revoke(context, context.device.pk)
            return Response(status=204)
        raise Problem("Не найдено.", 404, "not_found")


@method_decorator(never_cache, name="dispatch")
class StaffMobileSessionView(APIView):
    authentication_classes = [StaffBearerAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, pk=None):
        if pk:
            raise Problem("Используйте DELETE.", 405, "method_not_allowed")
        context = require_context(request)
        devices = StaffDevice.objects.filter(
            user=context.user,
            credential_version=staff_credential_version(context.user),
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at")
        return Response(
            {
                "sessions": [
                    {
                        "id": str(d.pk),
                        "name": d.name,
                        "createdAt": d.created_at.isoformat(),
                        "lastUsedAt": d.last_used_at.isoformat(),
                        "expiresAt": d.expires_at.isoformat(),
                        "current": d.pk == context.device.pk,
                    }
                    for d in devices
                ]
            }
        )

    def delete(self, request, pk=None):
        if not pk:
            raise Problem("Укажите сессию.", 405, "method_not_allowed")
        revoke(require_context(request), pk)
        return Response(status=204)
