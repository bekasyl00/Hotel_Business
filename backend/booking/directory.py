"""Platform-only guest directory. Identity/contact verification is not bypassed here."""

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from .errors import Problem
from .models import GuestAccount, GuestProfile
from .serializers import guest_profile_data
from .services import log_change, require_admin, version_check


def account_summary(account):
    if account is None:
        return None
    return {
        "id": account.pk,
        "status": "active" if account.is_active else "disabled",
        "version": account.version,
        "createdAt": account.created_at.isoformat(),
    }


def clients(request):
    require_admin(request.user)
    page = serializers.IntegerField(min_value=1, max_value=100000).run_validation(
        request.query_params.get("page", 1)
    )
    search = serializers.CharField(max_length=100, allow_blank=True).run_validation(
        request.query_params.get("q", "")
    )
    items = GuestProfile.objects.select_related("account").annotate(booking_count=Count("bookings"))
    if search:
        items = items.filter(Q(name__icontains=search) | Q(phone__icontains=search))
    items = items.order_by("-created_at", "id")
    return {
        "count": items.count(),
        "page": page,
        "pageSize": 25,
        "items": [
            {
                "profile": guest_profile_data(item),
                "account": account_summary(getattr(item, "account", None)),
                "bookingCount": item.booking_count,
            }
            for item in items[(page - 1) * 25 : page * 25]
        ],
    }


@transaction.atomic
def set_client_status(request, pk):
    require_admin(request.user)
    item = get_object_or_404(GuestAccount.objects.select_for_update(), profile_id=pk)
    version_check(item, request.data)
    status = serializers.ChoiceField(choices=["active", "disabled"]).run_validation(
        request.data.get("status")
    )
    if set(request.data) != {"status", "version"}:
        raise Problem("Допустимы только статус и версия.")
    before = account_summary(item)
    item.is_active = status == "active"
    item.auth_version += 1
    item.version += 1
    item.save(update_fields=["is_active", "auth_version", "version"])
    after = account_summary(item)
    log_change(request.user, "guestAccounts", item, "access", before, after)
    return after
