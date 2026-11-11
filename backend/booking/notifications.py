import hashlib
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .errors import Problem
from .models import (
    Resort,
    StaffNotification,
    StaffPushDelivery,
    StaffPushDevice,
    User,
)


def is_operational_staff(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "role", None) != "accountant"
        and (getattr(user, "role", None) in ("admin", "manager") or getattr(user, "is_superuser", False))
    )


def require_operational_staff(user):
    if not user or not getattr(user, "is_authenticated", False):
        raise Problem("Войдите в аккаунт сотрудника.", 401, "unauthorized")
    if getattr(user, "role", None) == "accountant" or not is_operational_staff(user):
        raise Problem("Недостаточно прав для этого раздела.", 403, "forbidden")


def accessible_resorts_for_notifications(user):
    require_operational_staff(user)
    if getattr(user, "role", None) == "admin" or getattr(user, "is_superuser", False):
        return Resort.objects.all()
    return Resort.objects.filter(account=user)


def notification_recipients_for_resort(resort: Resort):
    recipients = {}
    if resort.account_id:
        owner = (
            User.objects.filter(pk=resort.account_id, is_active=True)
            .exclude(role="accountant")
            .first()
        )
        if owner is not None:
            recipients[owner.pk] = owner
    for admin_user in (
        User.objects.filter(is_active=True)
        .filter(Q(role="admin") | Q(is_superuser=True))
        .exclude(role="accountant")
    ):
        recipients[admin_user.pk] = admin_user
    return list(recipients.values())


def _booking_place_summary(booking):
    snap = booking.snapshot if isinstance(booking.snapshot, dict) else {}
    place_ids = list(snap.get("placeIds") or [])
    place_labels = list(snap.get("placeLabels") or [])
    if not place_labels:
        allocations = list(
            booking.allocations.select_related("place").order_by("place__position", "place_id")
        )
        if allocations:
            place_ids = [a.place_id for a in allocations]
            place_labels = [f"{booking.room.number}{a.place.label}" for a in allocations]
    return place_ids, place_labels


def emit_booking_notification(booking, kind: str):
    if kind not in (
        "booking_created",
        "booking_paid",
        "booking_cancelled",
        "booking_expired",
    ):
        raise ValueError(f"Unsupported notification kind: {kind}")

    resort = booking.resort
    place_ids, place_labels = _booking_place_summary(booking)
    payload = {
        "bookingId": booking.pk,
        "resortId": resort.pk,
        "resortName": resort.name,
        "roomId": booking.room_id,
        "roomNumber": booking.room.number,
        "placeIds": place_ids,
        "placeLabels": place_labels,
        "placesCount": len(place_labels) or int(booking.guests or 1),
        "start": str(booking.stay.lower),
        "end": str(booking.stay.upper),
        "guests": int(booking.guests or 1),
        "status": booking.status,
        "source": booking.source,
    }

    created_notifications = []
    recipients = notification_recipients_for_resort(resort)
    for recipient in recipients:
        dedup_key = f"{booking.pk}:{kind}:{recipient.pk}"
        notification, created = StaffNotification.objects.get_or_create(
            dedup_key=dedup_key,
            defaults={
                "recipient": recipient,
                "resort": resort,
                "booking": booking,
                "kind": kind,
                "payload": payload,
            },
        )
        if created:
            created_notifications.append(notification)
            active_devices = list(
                StaffPushDevice.objects.filter(user=recipient, is_active=True)
            )
            push_configured = bool(
                getattr(settings, "FCM_SERVER_CREDENTIAL", "")
                or getattr(settings, "APNS_KEY_ID", "")
            )
            for device in active_devices:
                StaffPushDelivery.objects.get_or_create(
                    dedup_key=f"push:{notification.pk}:{device.pk}",
                    defaults={
                        "notification": notification,
                        "device": device,
                        "status": "pending" if push_configured else "skipped_unconfigured",
                    },
                )
    return created_notifications


def notification_data(item: StaffNotification):
    payload = item.payload if isinstance(item.payload, dict) else {}
    unit = payload.get("roomNumber") or payload.get("unit") or ""
    resort_name = payload.get("resortName", "")
    start = payload.get("start", "")
    end = payload.get("end", "")
    places_count = payload.get("placesCount", 1)
    place_labels = payload.get("placeLabels", [])
    labels_str = ", ".join(place_labels) if isinstance(place_labels, list) else ""
    titles = {
        "booking_created": f"Новая бронь № {unit}",
        "booking_paid": f"Бронь оплачена № {unit}",
        "booking_cancelled": f"Бронь отменена № {unit}",
        "booking_expired": f"Истёк резерв № {unit}",
    }
    title = titles.get(item.kind, f"Событие брони № {unit}")
    body = (
        f"{resort_name} · № {unit}"
        f"{f' ({labels_str})' if labels_str else ''}"
        f" · {start} — {end} · мест: {places_count}"
    )
    return {
        "id": item.pk,
        "kind": item.kind,
        "title": title,
        "body": body,
        "resortId": item.resort_id,
        "bookingId": item.booking_id,
        "read": item.read_at is not None,
        "readAt": item.read_at.isoformat() if item.read_at else None,
        "createdAt": item.created_at.isoformat(),
        "payload": {
            "bookingId": payload.get("bookingId", item.booking_id),
            "resortId": payload.get("resortId", item.resort_id),
            "resortName": resort_name,
            "roomId": payload.get("roomId", ""),
            "roomNumber": unit,
            "unit": unit,
            "placeIds": payload.get("placeIds", []),
            "placeLabels": place_labels,
            "placesCount": places_count,
            "start": start,
            "end": end,
            "guests": payload.get("guests", 1),
            "status": payload.get("status", ""),
            "source": payload.get("source", ""),
        },
    }


def scoped_notifications_queryset(user):
    resorts = accessible_resorts_for_notifications(user)
    return StaffNotification.objects.filter(recipient=user, resort__in=resorts)


def unread_notification_count(user) -> int:
    if not is_operational_staff(user):
        return 0
    return scoped_notifications_queryset(user).filter(read_at__isnull=True).count()


def list_staff_notifications(user, *, cursor="", limit=30, unread_only=False, resort_id=""):
    qs = scoped_notifications_queryset(user)
    if resort_id:
        qs = qs.filter(resort_id=resort_id)
    if unread_only:
        qs = qs.filter(read_at__isnull=True)

    try:
        bounded_limit = max(1, min(int(limit or 30), 50))
    except (TypeError, ValueError):
        raise Problem("Некорректный лимит списка уведомлений.", 422, "validation_error")

    if cursor:
        raw = str(cursor).strip()
        if "|" in raw:
            ts_part, id_part = raw.split("|", 1)
            try:
                parsed_ts = datetime.fromisoformat(ts_part)
            except ValueError:
                raise Problem("Некорректный курсор уведомлений.", 422, "validation_error")
            qs = qs.filter(
                Q(created_at__lt=parsed_ts) | Q(created_at=parsed_ts, pk__lt=id_part)
            )
        else:
            anchor = StaffNotification.objects.filter(pk=raw, recipient=user).first()
            if anchor is None:
                raise Problem("Некорректный курсор уведомлений.", 422, "validation_error")
            qs = qs.filter(
                Q(created_at__lt=anchor.created_at)
                | Q(created_at=anchor.created_at, pk__lt=anchor.pk)
            )

    rows = list(qs.order_by("-created_at", "-id")[: bounded_limit + 1])
    has_more = len(rows) > bounded_limit
    items = rows[:bounded_limit]
    next_cursor = (
        f"{items[-1].created_at.isoformat()}|{items[-1].pk}" if has_more and items else None
    )
    return {
        "items": [notification_data(item) for item in items],
        "nextCursor": next_cursor,
        "unreadCount": unread_notification_count(user),
    }


@transaction.atomic
def mark_notification_read(user, notification_id: str):
    qs = scoped_notifications_queryset(user).select_for_update()
    item = qs.filter(pk=notification_id).first()
    if item is None:
        if StaffNotification.objects.filter(pk=notification_id).exists():
            raise Problem("Уведомление недоступно.", 403, "forbidden")
        raise Problem("Уведомление не найдено.", 404, "not_found")
    if item.read_at is None:
        item.read_at = timezone.now()
        item.version += 1
        item.save(update_fields=["read_at", "version"])
    data = notification_data(item)
    return {
        **data,
        "notification": data,
        "unreadCount": unread_notification_count(user),
    }


@transaction.atomic
def mark_all_notifications_read(user, *, resort_id=""):
    qs = scoped_notifications_queryset(user).filter(read_at__isnull=True)
    if resort_id:
        qs = qs.filter(resort_id=resort_id)
    now = timezone.now()
    updated = qs.update(read_at=now)
    return {
        "updated": updated,
        "markedCount": updated,
        "unreadCount": unread_notification_count(user),
    }


def push_device_data(device: StaffPushDevice):
    return {
        "id": device.pk,
        "platform": device.platform,
        "deviceLabel": device.device_label,
        "appVersion": device.app_version,
        "isActive": device.is_active,
        "status": "active" if device.is_active else "revoked",
        "updatedAt": device.updated_at.isoformat(),
    }


@transaction.atomic
def register_staff_push_device(user, payload: dict):
    require_operational_staff(user)
    if not isinstance(payload, dict):
        raise Problem("Некорректные данные устройства.", 422, "validation_error")
    allowed = {"platform", "pushToken", "token", "deviceLabel", "appVersion"}
    if set(payload) - allowed:
        raise Problem("Неизвестные поля регистрации push-устройства.", 422, "validation_error")
    platform = str(payload.get("platform") or "").strip().lower()
    if platform not in ("ios", "android"):
        raise Problem("Платформа push-уведомлений должна быть ios или android.", 422, "validation_error")
    push_token = str(payload.get("pushToken") or payload.get("token") or "").strip()
    if len(push_token) < 16 or len(push_token) > 512 or any(ch.isspace() for ch in push_token):
        raise Problem("Некорректный push-токен устройства.", 422, "validation_error")
    device_label = str(payload.get("deviceLabel") or "").strip()[:120]
    app_version = str(payload.get("appVersion") or "").strip()[:40]
    token_hash = hashlib.sha256(f"{platform}:{push_token}".encode()).hexdigest()

    device, _ = StaffPushDevice.objects.select_for_update().update_or_create(
        token_hash=token_hash,
        defaults={
            "user": user,
            "platform": platform,
            "push_token": push_token,
            "device_label": device_label,
            "app_version": app_version,
            "is_active": True,
            "revoked_at": None,
        },
    )
    return push_device_data(device)


@transaction.atomic
def revoke_staff_push_device(user, device_id: str):
    require_operational_staff(user)
    device = (
        StaffPushDevice.objects.select_for_update()
        .filter(pk=device_id, user=user)
        .first()
    )
    if device is None:
        raise Problem("Push-устройство не найдено.", 404, "not_found")
    if device.is_active:
        device.is_active = False
        device.revoked_at = timezone.now()
        device.version += 1
        device.save(update_fields=["is_active", "revoked_at", "version", "updated_at"])
    return push_device_data(device)
