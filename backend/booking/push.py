"""Durable staff system-push delivery: FCM HTTP v1 (Android) and APNs token auth (iOS).

Deliveries are created by notifications.emit_booking_notification inside the booking
transaction and sent later by the scheduler tick or `manage.py send_staff_push`.
Alerts carry no guest personal data; the tap payload is only notification/booking ids.
"""

import base64
import json
import logging
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import StaffPushDelivery

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
TIMEOUT = 10
_token_cache = {}

SENT, INVALID, RETRY = "sent", "invalid_token", "retry"


def _service_account():
    raw = settings.FCM_SERVICE_ACCOUNT_JSON.strip()
    if not raw:
        return None
    if not raw.startswith("{"):
        raw = base64.b64decode(raw).decode()
    return json.loads(raw)


def platform_configured(platform: str) -> bool:
    if platform == "android":
        return bool(settings.FCM_SERVICE_ACCOUNT_JSON)
    if platform == "ios":
        return bool(settings.APNS_KEY_ID and settings.APNS_TEAM_ID and settings.APNS_PRIVATE_KEY)
    return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwt(header: dict, claims: dict, sign) -> str:
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    return f"{signing_input}.{_b64(sign(signing_input.encode()))}"


def _cached(key, ttl, build):
    hit = _token_cache.get(key)
    if hit and hit[1] > time.time():
        return hit[0]
    value = build()
    _token_cache[key] = (value, time.time() + ttl)
    return value


def _fcm_access_token(client, account):
    def build():
        key = serialization.load_pem_private_key(account["private_key"].encode(), None)
        now = int(time.time())
        assertion = _jwt(
            {"alg": "RS256", "typ": "JWT"},
            {
                "iss": account["client_email"],
                "scope": "https://www.googleapis.com/auth/firebase.messaging",
                "aud": account["token_uri"],
                "iat": now,
                "exp": now + 3600,
            },
            lambda data: key.sign(data, padding.PKCS1v15(), hashes.SHA256()),
        )
        response = client.post(
            account["token_uri"],
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    return _cached(("fcm", account["client_email"]), 3000, build)


def _apns_jwt():
    def build():
        key = serialization.load_pem_private_key(settings.APNS_PRIVATE_KEY.encode(), None)

        def sign(data):
            r, s = decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256())))
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")

        return _jwt(
            {"alg": "ES256", "kid": settings.APNS_KEY_ID},
            {"iss": settings.APNS_TEAM_ID, "iat": int(time.time())},
            sign,
        )

    # Apple rejects tokens older than one hour and throttles refreshes faster than 20 minutes.
    return _cached(("apns", settings.APNS_KEY_ID), 2400, build)


def _send_fcm(client, token, title, body, data):
    account = _service_account()
    response = client.post(
        f"https://fcm.googleapis.com/v1/projects/{account['project_id']}/messages:send",
        headers={"Authorization": f"Bearer {_fcm_access_token(client, account)}"},
        json={
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": data,
                "android": {"priority": "HIGH", "notification": {"channel_id": "bookings"}},
            }
        },
        timeout=TIMEOUT,
    )
    if response.status_code == 200:
        return SENT, ""
    detail = response.text[:200]
    if response.status_code == 404 or "UNREGISTERED" in detail or (
        response.status_code == 400 and "registration token" in detail.lower()
    ):
        return INVALID, f"fcm {response.status_code}"
    return RETRY, f"fcm {response.status_code} {detail}"


def _send_apns(client, token, title, body, data):
    host = "api.sandbox.push.apple.com" if settings.APNS_USE_SANDBOX else "api.push.apple.com"
    response = client.post(
        f"https://{host}/3/device/{token}",
        headers={
            "authorization": f"bearer {_apns_jwt()}",
            "apns-topic": settings.APNS_TOPIC,
            "apns-push-type": "alert",
            "apns-priority": "10",
        },
        json={"aps": {"alert": {"title": title, "body": body}, "sound": "default"}, **data},
        timeout=TIMEOUT,
    )
    if response.status_code == 200:
        return SENT, ""
    reason = ""
    try:
        reason = response.json().get("reason", "")
    except ValueError:
        pass
    if response.status_code == 410 or reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
        return INVALID, f"apns {response.status_code} {reason}"
    return RETRY, f"apns {response.status_code} {reason}"


def _http_client():
    return httpx.Client(http2=True)


def _recipient_still_allowed(delivery) -> bool:
    notification, device = delivery.notification, delivery.device
    user = notification.recipient
    if not device.is_active or device.user_id != user.pk or not user.is_active:
        return False
    if user.role == "accountant":
        return False
    if user.role == "admin" or user.is_superuser:
        return True
    return notification.resort.account_id == user.pk


def _deliver_one(client) -> bool:
    from .notifications import notification_data

    # Row lock is held during the send so overlapping ticks never push the same delivery twice.
    with transaction.atomic():
        delivery = (
            StaffPushDelivery.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("notification__recipient", "notification__resort", "device")
            .filter(status="pending", attempts__lt=MAX_ATTEMPTS)
            .order_by("created_at")
            .first()
        )
        if delivery is None:
            return False
        delivery.attempts += 1
        fields = ["attempts", "status", "last_error", "sent_at"]
        platform = delivery.device.platform
        if not _recipient_still_allowed(delivery):
            delivery.status, delivery.last_error = "failed", "recipient_not_allowed"
        elif not platform_configured(platform):
            delivery.status, delivery.last_error = "skipped_unconfigured", ""
        else:
            item = notification_data(delivery.notification)
            data = {
                "notificationId": str(delivery.notification_id),
                "bookingId": str(delivery.notification.booking_id or ""),
                "resortId": str(delivery.notification.resort_id),
            }
            send = _send_fcm if platform == "android" else _send_apns
            try:
                outcome, error = send(client, delivery.device.push_token, item["title"], item["body"], data)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                outcome, error = RETRY, f"{type(exc).__name__}"
            delivery.last_error = error[:240]
            if outcome == SENT:
                delivery.status, delivery.sent_at = "sent", timezone.now()
            elif outcome == INVALID:
                delivery.status = "failed"
                device = delivery.device
                device.is_active, device.revoked_at = False, timezone.now()
                device.save(update_fields=["is_active", "revoked_at", "updated_at"])
            elif delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = "failed"
            if outcome != SENT:
                logger.warning("staff push %s: %s", delivery.pk, delivery.last_error)
        delivery.save(update_fields=fields)
    return True


def send_due_pushes(limit=50, deadline=None) -> int:
    count = 0
    with _http_client() as client:
        while count < limit and (deadline is None or time.monotonic() < deadline):
            if not _deliver_one(client):
                break
            count += 1
    return count
