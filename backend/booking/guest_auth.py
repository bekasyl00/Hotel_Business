"""Guest identity is separate from Django's staff User and never grants staff roles."""

import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.middleware.csrf import rotate_token
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import Problem
from .models import Audit, Booking, GuestAccount, GuestChallenge, GuestProfile, LoginAttempt
from .serializers import guest_profile_data

AUTH_KEY = "guest_account"
SCOPE_KEY = "guest_challenge_scope"
CHALLENGE_TTL = timedelta(minutes=5)
RESEND_SECONDS = 60
MAX_CODE_ATTEMPTS = 5


def digest(value):
    return salted_hmac("guest-auth", value, algorithm="sha256").hexdigest()


def demo_enabled():
    return settings.DEBUG and settings.GUEST_AUTH_DEMO_OTP


class DemoCodeDelivery:
    """Delivery seam: a future verified SMS provider must replace this implementation."""

    def send_code(self, phone, code):
        return {"mode": "demo", "demoCode": code}


def code_delivery():
    if not demo_enabled():
        raise Problem(
            "Отправка SMS пока не подключена. Регистрация и восстановление недоступны.",
            503,
            "sms_unavailable",
        )
    return DemoCodeDelivery()


def normalize_phone(value):
    if not isinstance(value, str) or len(value) > 32:
        raise Problem("Укажите мобильный номер Казахстана: +7 7XX XXX XX XX.", 422, "phone_invalid")
    phone = re.sub(r"[\s()\-]", "", value)
    if len(phone) == 11 and phone.startswith("8"):
        phone = "+7" + phone[1:]
    if not re.fullmatch(r"\+77[0-9]{9}", phone):
        raise Problem("Укажите мобильный номер Казахстана: +7 7XX XXX XX XX.", 422, "phone_invalid")
    return phone


def payload(request, keys):
    data = request.data
    if not isinstance(data, dict) or set(data) != set(keys):
        raise Problem("Проверьте заполнение полей.", 422, "invalid_request")
    return data


def password_value(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise Problem("Пароль должен содержать от 12 до 128 символов.", 422, "weak_password")
    try:
        validate_password(value)
    except ValidationError as exc:
        raise Problem(" ".join(exc.messages), 422, "weak_password") from exc
    return value


def clear_guest(request, *, rotate_session=True):
    for key in [AUTH_KEY, SCOPE_KEY, "guest_owner"]:
        request.session.pop(key, None)
    if rotate_session:
        request.session.cycle_key()
    rotate_token(request)


def current_account(request):
    identity = request.session.get(AUTH_KEY)
    if identity is None:
        return None
    account = (
        GuestAccount.objects.select_related("profile").filter(pk=identity.get("id")).first()
        if isinstance(identity, dict)
        else None
    )
    if not account or not account.is_active or identity.get("version") != account.auth_version:
        # Ownership is also resolved inside domain transactions which may roll back.
        # Let SessionMiddleware persist this invalidation outside that transaction.
        clear_guest(request, rotate_session=False)
        return None
    return account


def session_data(request, account=None):
    account = account or current_account(request)
    return {
        "authenticated": bool(account),
        "account": {"id": account.pk, "phone": account.phone} if account else None,
        "profile": guest_profile_data(account.profile) if account else None,
        "mode": "demo" if demo_enabled() else "disabled",
    }


def establish_session(request, account):
    clear_guest(request)
    request.session[AUTH_KEY] = {"id": account.pk, "version": account.auth_version}
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    return session_data(request, account)


def audit(account, action):
    Audit.objects.create(
        actor="Гость сайта",
        entity="guestAccounts",
        entity_id=account.pk,
        action=action,
        label="Гостевой аккаунт",
        before=None,
        after={"id": account.pk, "authVersion": account.auth_version},
    )


def enforce_limit(request, prefix, phone=None, phone_limit=10, ip_limit=30, minutes=15):
    now = timezone.now()
    keys = [(digest(prefix + ":ip:" + request.META.get("REMOTE_ADDR", "")), ip_limit)]
    if phone:
        keys.append((digest(prefix + ":phone:" + phone), phone_limit))
    limited = False
    with transaction.atomic():
        for key, limit in sorted(keys):
            LoginAttempt.objects.get_or_create(key=key, defaults={"since": now})
            row = LoginAttempt.objects.select_for_update().get(pk=key)
            if row.since <= now - timedelta(minutes=minutes):
                row.count, row.since = 0, now
            if row.count >= limit:
                limited = True
            else:
                row.count += 1
            row.save()
    if limited:
        raise Problem("Слишком много попыток. Повторите позже.", 429, "rate_limited")


def issue_challenge(request):
    from .services import guest_owner

    data = payload(request, ["phone", "purpose"])
    phone = normalize_phone(data["phone"])
    if data["purpose"] not in ["register", "reset"]:
        raise Problem("Неверный тип подтверждения.", 422, "invalid_request")
    provider = code_delivery()
    enforce_limit(request, "guest-otp", phone, phone_limit=5, minutes=60)
    owner = guest_owner(request)
    scope = request.session.get(SCOPE_KEY)
    if not scope:
        scope = secrets.token_hex(32)
        request.session[SCOPE_KEY] = scope
    now = timezone.now()
    code = f"{secrets.randbelow(1000000):06d}"
    # This per-phone row serializes sends, resend invalidation and verification across workers.
    phone_key = digest("guest-challenge:" + phone)
    with transaction.atomic():
        LoginAttempt.objects.get_or_create(key=phone_key, defaults={"since": now})
        LoginAttempt.objects.select_for_update().get(pk=phone_key)
        latest = (
            GuestChallenge.objects.filter(phone=phone, purpose=data["purpose"])
            .order_by("-created_at")
            .first()
        )
        if latest and latest.created_at > now - timedelta(seconds=RESEND_SECONDS):
            raise Problem("Повторный код доступен через 60 секунд.", 429, "resend_cooldown")
        GuestChallenge.objects.filter(
            phone=phone, purpose=data["purpose"], consumed_at__isnull=True
        ).update(consumed_at=now)
        challenge = GuestChallenge.objects.create(
            phone=phone,
            purpose=data["purpose"],
            scope_hash=digest(scope),
            owner=owner,
            code_hash=make_password(code),
            expires_at=now + CHALLENGE_TTL,
        )
        delivery = provider.send_code(phone, code)
    return {
        "challengeId": challenge.pk,
        "expiresAt": challenge.expires_at.isoformat(),
        "retryAfterSeconds": RESEND_SECONDS,
        "message": "Если действие доступно для этого номера, используйте код подтверждения.",
        **delivery,
    }


def invalid_code(code="invalid_code"):
    return Problem("Код неверен или больше не действует. Запросите новый код.", 422, code)


def locked_challenge(request, data, purpose):
    challenge_id, code = data["challengeId"], data["code"]
    if not isinstance(challenge_id, str) or len(challenge_id) > 64:
        return None, invalid_code()
    phone = GuestChallenge.objects.filter(pk=challenge_id).values_list("phone", flat=True).first()
    if not phone:
        return None, invalid_code()
    LoginAttempt.objects.select_for_update().get(pk=digest("guest-challenge:" + phone))
    challenge = GuestChallenge.objects.select_for_update().get(pk=challenge_id)
    scope = request.session.get(SCOPE_KEY, "")
    if challenge.purpose != purpose or not secrets.compare_digest(
        challenge.scope_hash, digest(scope)
    ):
        return None, invalid_code()
    if challenge.consumed_at or challenge.attempts >= MAX_CODE_ATTEMPTS:
        return None, invalid_code()
    if challenge.expires_at <= timezone.now():
        return None, invalid_code("code_expired")
    challenge.attempts += 1
    challenge.save(update_fields=["attempts"])
    if (
        not isinstance(code, str)
        or not re.fullmatch(r"[0-9]{6}", code)
        or not check_password(code, challenge.code_hash)
    ):
        return None, invalid_code()
    return challenge, None


def register(request):
    from .services import guest_owner

    code_delivery()
    data = payload(request, ["challengeId", "code", "name", "password"])
    password = password_value(data["password"])
    name = data["name"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise Problem("Укажите имя длиной до 80 символов.", 422, "name_invalid")
    if current_account(request):
        raise Problem(
            "Сначала выйдите из текущего гостевого аккаунта.", 409, "already_authenticated"
        )
    enforce_limit(request, "guest-verify", ip_limit=60)
    owner = guest_owner(request)
    with transaction.atomic():
        challenge, error = locked_challenge(request, data, "register")
        if not error:
            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at"])
            if (
                challenge.owner != owner
                or GuestAccount.objects.filter(phone=challenge.phone).exists()
            ):
                error = invalid_code()
            else:
                profile, _ = GuestProfile.objects.get_or_create(
                    owner=owner, defaults={"name": "", "phone": ""}
                )
                profile = GuestProfile.objects.select_for_update().get(pk=profile.pk)
                if GuestAccount.objects.filter(profile=profile).exists():
                    error = invalid_code()
                else:
                    new_owner = secrets.token_hex(32)
                    Booking.objects.filter(
                        guest_profile=profile, source="website", owner=owner
                    ).update(owner=new_owner)
                    profile.owner, profile.name, profile.phone = (
                        new_owner,
                        name.strip(),
                        challenge.phone,
                    )
                    profile.version += 1
                    profile.save()
                    account = GuestAccount.objects.create(
                        phone=challenge.phone, password=make_password(password), profile=profile
                    )
                    audit(account, "register")
    if error:
        raise error
    return establish_session(request, account)


def login(request):
    data = payload(request, ["phone", "password"])
    phone = normalize_phone(data["phone"])
    password = data["password"]
    if not isinstance(password, str) or len(password) > 128:
        raise Problem("Неверный телефон или пароль.", 401, "invalid_credentials")
    enforce_limit(request, "guest-login", phone)
    with transaction.atomic():
        account = (
            GuestAccount.objects.select_for_update()
            .select_related("profile")
            .filter(phone=phone)
            .first()
        )
        if account:
            valid = check_password(password, account.password) and account.is_active
        else:
            make_password(password)
            valid = False
        if not valid:
            raise Problem("Неверный телефон или пароль.", 401, "invalid_credentials")
        audit(account, "login")
        return establish_session(request, account)


def reset(request):
    code_delivery()
    data = payload(request, ["challengeId", "code", "password"])
    password = password_value(data["password"])
    enforce_limit(request, "guest-verify", ip_limit=60)
    encoded_password = make_password(password)
    with transaction.atomic():
        challenge, error = locked_challenge(request, data, "reset")
        if not error:
            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at"])
            account = GuestAccount.objects.select_for_update().filter(phone=challenge.phone).first()
            if account:
                account.password = encoded_password
                account.auth_version += 1
                account.save(update_fields=["password", "auth_version"])
                audit(account, "reset_password")
    if error:
        raise error
    current_account(request)
    return {"ok": True, "mode": "demo" if demo_enabled() else "disabled"}


@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class GuestAuthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, action):
        if action != "session":
            raise Problem("Для этого действия используйте POST.", 405, "method_not_allowed")
        return Response(session_data(request))

    def post(self, request, action):
        handlers = {
            "challenges": issue_challenge,
            "register": register,
            "login": login,
            "reset": reset,
        }
        if action == "logout":
            account = current_account(request)
            if account:
                audit(account, "logout")
            clear_guest(request)
            return Response(session_data(request))
        if action not in handlers:
            raise Problem("Не найдено.", 404, "not_found")
        return Response(handlers[action](request), status=201 if action == "register" else 200)
