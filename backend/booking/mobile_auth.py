"""Native guest login and revocable token families; web cookies are not consumed here."""

import re
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from identity.models import GuestDevice, GuestRefreshToken

from .authentication import GuestBearerAuthentication, bearer_context, invalid_token, token_hash
from .errors import Problem
from .guest_auth import audit, enforce_limit, normalize_phone, payload
from .models import GuestAccount
from .serializers import guest_profile_data

ACCESS_TTL = timedelta(minutes=15)
FAMILY_TTL = timedelta(days=30)


def tokens(device, now):
    access = "tg_a_" + secrets.token_urlsafe(32)
    refresh = "tg_r_" + secrets.token_urlsafe(32)
    device.access_hash = token_hash(access)
    device.access_expires_at = min(now + ACCESS_TTL, device.expires_at)
    device.last_used_at = now
    device.save()
    GuestRefreshToken.objects.create(token_hash=token_hash(refresh), device=device)
    return {
        "tokenType": "Bearer",
        "accessToken": access,
        "refreshToken": refresh,
        "expiresIn": int((device.access_expires_at - now).total_seconds()),
        "refreshExpiresAt": device.expires_at.isoformat(),
        "deviceId": str(device.pk),
        "account": {"id": device.account_id, "phone": device.account.phone},
        "profile": guest_profile_data(device.account.profile),
    }


def login(request):
    data = payload(request, ["phone", "password", "deviceName"])
    phone = normalize_phone(data["phone"])
    password, name = data["password"], data["deviceName"]
    if not isinstance(password, str) or len(password) > 128:
        raise Problem("Неверный телефон или пароль.", 401, "invalid_credentials")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise Problem("Укажите название устройства длиной до 80 символов.", 422, "invalid_request")
    # Shared web/native credential budget prevents bypassing login limits by switching APIs.
    enforce_limit(request, "guest-login", phone)
    with transaction.atomic():
        account = (
            GuestAccount.objects.select_for_update()
            .select_related("profile")
            .filter(phone=phone)
            .first()
        )
        if account:
            valid = check_password(password, account.password)
        else:
            make_password(password)
            valid = False
        if not valid or not account.is_active:
            raise Problem("Неверный телефон или пароль.", 401, "invalid_credentials")
        now = timezone.now()
        device = GuestDevice(
            account=account,
            name=name.strip(),
            auth_version=account.auth_version,
            expires_at=now + FAMILY_TTL,
        )
        result = tokens(device, now)
        audit(account, "native_login")
    return result


def refresh(request):
    data = payload(request, ["refreshToken"])
    value = data["refreshToken"]
    if not isinstance(value, str) or not re.fullmatch(r"tg_r_[A-Za-z0-9_-]{43}", value):
        raise invalid_token()
    enforce_limit(request, "guest-refresh", ip_limit=120)
    saved = (
        GuestRefreshToken.objects.filter(token_hash=token_hash(value))
        .select_related("device")
        .first()
    )
    if not saved:
        raise invalid_token()
    error = None
    with transaction.atomic():
        # Same account-first lock ordering as password reset and credential login.
        account = (
            GuestAccount.objects.select_for_update()
            .select_related("profile")
            .get(pk=saved.device.account_id)
        )
        device = GuestDevice.objects.select_for_update().get(pk=saved.device_id)
        saved = GuestRefreshToken.objects.select_for_update().get(pk=saved.pk)
        now = timezone.now()
        if (
            device.revoked_at
            or device.expires_at <= now
            or not account.is_active
            or device.auth_version != account.auth_version
            or saved.consumed_at
        ):
            if not device.revoked_at:
                device.revoked_at = now
                device.save(update_fields=["revoked_at"])
                if saved.consumed_at:
                    audit(account, "native_refresh_reuse")
            error = invalid_token()
        else:
            saved.consumed_at = now
            saved.save(update_fields=["consumed_at"])
            device.account = account
            result = tokens(device, now)
    # Raise after commit so replay revocation cannot accidentally roll back.
    if error:
        raise error
    return result


def require_context(request):
    context = bearer_context(request)
    if not context:
        raise invalid_token()
    return context


@transaction.atomic
def revoke_session(context, device_id, action):
    account = GuestAccount.objects.select_for_update().get(pk=context.account.pk)
    device = GuestDevice.objects.select_for_update().filter(pk=device_id, account=account).first()
    if not device:
        raise Problem("Не найдено.", 404, "not_found")
    if not device.revoked_at:
        device.revoked_at = timezone.now()
        device.save(update_fields=["revoked_at"])
        audit(account, action)


@method_decorator(never_cache, name="dispatch")
class MobileAuthView(APIView):
    authentication_classes = [GuestBearerAuthentication]
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
            revoke_session(context, context.device.pk, "native_logout")
            return Response(status=204)
        raise Problem("Не найдено.", 404, "not_found")


@method_decorator(never_cache, name="dispatch")
class MobileSessionView(APIView):
    authentication_classes = [GuestBearerAuthentication]
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def get(self, request, pk=None):
        if pk:
            raise Problem("Для этого действия используйте DELETE.", 405, "method_not_allowed")
        context = require_context(request)
        now = timezone.now()
        devices = GuestDevice.objects.filter(
            account=context.account,
            auth_version=context.account.auth_version,
            revoked_at__isnull=True,
            expires_at__gt=now,
        ).order_by("-created_at")
        return Response(
            {
                "sessions": [
                    {
                        "id": str(item.pk),
                        "name": item.name,
                        "createdAt": item.created_at.isoformat(),
                        "lastUsedAt": item.last_used_at.isoformat(),
                        "expiresAt": item.expires_at.isoformat(),
                        "current": item.pk == context.device.pk,
                    }
                    for item in devices
                ]
            }
        )

    def delete(self, request, pk=None):
        if not pk:
            raise Problem("Укажите сессию устройства.", 405, "method_not_allowed")
        context = require_context(request)
        revoke_session(context, pk, "native_revoke")
        return Response(status=204)
