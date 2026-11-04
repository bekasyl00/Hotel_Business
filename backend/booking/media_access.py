import re
from datetime import timedelta
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .errors import Problem
from .models import Booking, GuestProfile, MediaAsset, Resort, Review, Room

ASSET_PATH = re.compile(r"^/api/media/files/([a-f0-9-]{36})$")


def validate_asset_references(values, *, purpose, resort_id=None, booking_id=None):
    for value in values:
        url = value.get("url", "") if isinstance(value, dict) else value
        path = unquote(urlsplit(url).path)
        if not path.startswith(("/api/media/files/", "/api/v1/media/files/")):
            continue  # Existing illustrative catalogue URLs remain readable.
        # Only the stable canonical URL may reference a managed asset. Encoded or
        # absolute aliases would bypass both scope validation and cleanup checks.
        match = ASSET_PATH.fullmatch(url)
        asset = MediaAsset.objects.filter(pk=match[1]).first() if match else None
        if not asset or asset.purpose != purpose or str(asset.resort_id) != str(resort_id):
            raise Problem(
                "Этот файл недоступен для выбранного санатория.", 422, "media_scope_invalid"
            )
        if purpose == "review" and str(asset.booking_id) != str(booking_id):
            raise Problem("Фотография относится к другому проживанию.", 422, "media_scope_invalid")
        if isinstance(value, dict) and value.get("kind") != asset.kind:
            raise Problem("Тип файла не совпадает с загруженным.", 422, "media_type_invalid")


def asset_is_referenced(asset):
    if asset.purpose == "avatar":
        return GuestProfile.objects.filter(avatar=asset).exists()
    if asset.purpose == "review":
        return Review.objects.filter(
            booking_id=asset.booking_id, photos__contains=[asset.url]
        ).exists()
    return (
        Resort.objects.filter(pk=asset.resort_id, media__contains=[{"url": asset.url}]).exists()
        or Room.objects.filter(
            resort_id=asset.resort_id, media__contains=[{"url": asset.url}]
        ).exists()
    )


def can_read_asset(request, asset):
    from .services import admin, guest_owner

    staff = request.user.is_authenticated
    if asset.purpose == "avatar":
        if not GuestProfile.objects.filter(pk=asset.profile_id, avatar=asset).exists():
            return False
        if staff:
            return (
                admin(request.user)
                or Booking.objects.filter(
                    guest_profile_id=asset.profile_id,
                    resort_id=request.user.resort_id,
                    source="website",
                ).exists()
            )
        return asset.profile.owner == guest_owner(request)
    if staff and (admin(request.user) or str(request.user.resort_id) == str(asset.resort_id)):
        return True
    if asset.purpose == "review":
        if asset.booking.owner == guest_owner(request) and asset.booking.source == "website":
            return True
        return Review.objects.filter(
            booking_id=asset.booking_id,
            status="approved",
            resort__status="published",
            photos__contains=[asset.url],
        ).exists()
    if asset.resort.status != "published":
        return False
    return (
        Resort.objects.filter(pk=asset.resort_id, media__contains=[{"url": asset.url}]).exists()
        or Room.objects.filter(
            resort_id=asset.resort_id, status="active", media__contains=[{"url": asset.url}]
        ).exists()
    )


def enforce_upload_quota(*, purpose, incoming_size, resort=None, profile=None, booking=None):
    since = timezone.now() - timedelta(days=1)
    assets = MediaAsset.objects.filter(created_at__gte=since)
    if purpose == "catalog":
        assets = assets.filter(resort=resort, purpose="catalog")
        limit = settings.MEDIA_RESORT_DAILY_BYTES
    elif purpose == "avatar":
        assets = assets.filter(profile=profile, purpose="avatar")
        limit = settings.MEDIA_GUEST_DAILY_BYTES
    else:
        assets = assets.filter(booking=booking, purpose="review")
        limit = settings.MEDIA_GUEST_DAILY_BYTES
    used = assets.aggregate(total=Sum("size"))["total"] or 0
    if used + incoming_size > limit or assets.count() >= 100:
        raise Problem(
            "Лимит загрузок на сутки исчерпан. Попробуйте позже.", 429, "media_quota_exceeded"
        )
