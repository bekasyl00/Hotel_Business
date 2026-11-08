"""Self-service staff contact details and explicitly scoped document issuer settings."""

import re

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from commerce.accounting.services import StrictInput, company_data, save_company

from .authentication import bearer_or_csrf_protect
from .errors import Problem
from .guest_auth import enforce_limit
from .models import Audit, Resort, User
from .serializers import account_data
from .services import require_staff, scoped_resorts


class ProfileInput(StrictInput):
    version = serializers.IntegerField(min_value=1)
    accountVersion = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=100)
    jobTitle = serializers.CharField(max_length=100, allow_blank=True)
    contactPhone = serializers.CharField(max_length=30, allow_blank=True)

    def validate_contactPhone(self, value):
        if not value:
            return ""
        if not re.fullmatch(r"\+?[0-9 ()-]+", value):
            raise serializers.ValidationError("Укажите рабочий телефон с кодом страны.")
        digits = re.sub(r"[ ()-]", "", value).lstrip("+")
        if not re.fullmatch(r"[1-9][0-9]{6,14}", digits):
            raise serializers.ValidationError("Укажите рабочий телефон с кодом страны.")
        return "+" + digits


def profile_data(user):
    return {
        "id": str(user.pk),
        "version": user.profile_version,
        "accountVersion": user.version,
        "name": user.name,
        "jobTitle": user.job_title,
        "contactPhone": user.contact_phone,
        "login": user.email,
        "role": "admin" if user.is_superuser else user.role,
    }


@transaction.atomic
def update_profile(request):
    require_staff(request.user, roles=("admin", "manager", "accountant"))
    user = User.objects.select_for_update().get(pk=request.user.pk)
    require_staff(user, roles=("admin", "manager", "accountant"))
    inp = ProfileInput(data=request.data)
    inp.is_valid(raise_exception=True)
    data = inp.validated_data
    if data["version"] != user.profile_version or data["accountVersion"] != user.version:
        raise Problem("Профиль уже изменён. Обновите страницу.", 409, "staff_profile_conflict")
    before = user.profile_version
    user.name = data["name"]
    user.job_title = data["jobTitle"]
    user.contact_phone = data["contactPhone"]
    user.profile_version += 1
    user.save(update_fields=["name", "job_title", "contact_phone", "profile_version"])
    Audit.objects.create(
        actor=str(user.pk),
        resort=None,
        entity="staffProfile",
        entity_id=str(user.pk),
        action="update",
        label="Профиль сотрудника",
        before={"version": before},
        after={"version": user.profile_version},
    )
    return {"profile": profile_data(user), "account": account_data(user)}


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class StaffProfileView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        require_staff(request.user, roles=("admin", "manager", "accountant"))
        return Response(
            {
                "profile": profile_data(request.user),
                "resorts": list(
                    scoped_resorts(request.user).order_by("name", "id").values("id", "name")
                ),
            }
        )

    def patch(self, request):
        require_staff(request.user, roles=("admin", "manager", "accountant"))
        enforce_limit(request, "staff-profile-write", ip_limit=60, minutes=5)
        return Response(update_profile(request))


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class StaffCompanyView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def get(self, request, resort_id):
        require_staff(request.user, resort_id, roles=("admin", "manager", "accountant"))
        return Response(company_data(get_object_or_404(Resort, pk=resort_id)))

    def patch(self, request, resort_id):
        require_staff(request.user, roles=("admin", "manager", "accountant"))
        enforce_limit(request, "staff-company-write", ip_limit=60, minutes=5)
        return Response(save_company(request, resort_id, allow_manager=True))
