"""Platform operations console; domain writes stay in transactional services."""

import hashlib
import json
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Audit,
    Booking,
    GuestAccount,
    GuestProfile,
    LoginAttempt,
    MediaAsset,
    Resort,
    Review,
    Room,
    Tariff,
    User,
)


def workspace_url(path=""):
    base = getattr(settings, "STAFF_WORKSPACE_URL", "").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        return None
    return f"{base}/{path.lstrip('/')}" if path else base


class PlatformAuthenticationForm(AdminAuthenticationForm):
    def clean(self):
        email = str(self.data.get("username", "")).strip().lower()[:254]
        address = self.request.META.get("REMOTE_ADDR", "")
        keys = [
            hashlib.sha256(value.encode()).hexdigest()
            for value in (f"admin-email:{email}", f"admin-ip:{address}")
        ]
        now = timezone.now()
        with transaction.atomic():
            for key in sorted(keys):
                LoginAttempt.objects.get_or_create(key=key, defaults={"since": now})
                attempt = LoginAttempt.objects.select_for_update().get(pk=key)
                if attempt.since < now - timedelta(minutes=15):
                    attempt.count, attempt.since = 0, now
                if attempt.count >= 30:
                    raise ValidationError(
                        "Слишком много попыток входа. Повторите через 15 минут.",
                        code="rate_limited",
                    )
                attempt.count += 1
                attempt.save(update_fields=["count", "since"])
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise ValidationError(
                "Эта консоль доступна только суперпользователю платформы.",
                code="invalid_login",
            )


class PlatformAdminSite(admin.AdminSite):
    site_header = "Тыныс · управление платформой"
    site_title = "Тыныс Admin"
    index_title = "Операционная консоль"
    index_template = "admin/tynys/index.html"
    login_form = PlatformAuthenticationForm
    site_url = None

    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_staff and user.is_superuser

    def each_context(self, request):
        return {**super().each_context(request), "staff_workspace_url": workspace_url()}

    def index(self, request, extra_context=None):
        metrics = [
            ("Опубликованные санатории", Resort, {"status": "published"}),
            ("Заявки ждут решения", Booking, {"status": "pending"}),
            (
                "Гости проживают сейчас",
                Booking,
                {"checked_in_at__isnull": False, "checked_out_at__isnull": True},
            ),
            ("Отзывы ждут модерации", Review, {"status": "pending"}),
            ("Активные аккаунты гостей", GuestAccount, {"is_active": True}),
        ]
        cards = []
        for label, model, filters in metrics:
            opts = model._meta
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            cards.append(
                {
                    "label": label,
                    "count": model.objects.filter(**filters).count(),
                    "url": f"{url}?{urlencode(filters)}",
                }
            )
        return super().index(request, {**(extra_context or {}), "operation_cards": cards})

    def get_app_list(self, request, app_label=None):
        result = super().get_app_list(request, app_label)
        labels = {
            "User": "Сотрудники",
            "Resort": "Санатории",
            "Room": "Номера",
            "Tariff": "Тарифы",
            "Booking": "Бронирования и проживание",
            "GuestProfile": "Профили гостей",
            "GuestAccount": "Аккаунты гостей",
            "Review": "Отзывы",
            "Audit": "История изменений",
            "DemoPayment": "Платежи — симулятор",
            "DemoRefund": "Возвраты — симулятор",
            "MediaAsset": "Загруженные файлы",
        }
        for app in result:
            app["name"] = {"booking": "Каталог и бронирования", "commerce": "Демо-оплата"}.get(
                app["app_label"], app["name"]
            )
            for model in app["models"]:
                model["name"] = labels.get(model["object_name"], model["name"])
        return result


platform_admin_site = PlatformAdminSite(name="admin")


def record_link(item, label=None):
    if item is None:
        return "—"
    opts = item._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[item.pk])
    return format_html('<a href="{}">{}</a>', url, label or item.pk)


def structured_data(value):
    return format_html(
        '<pre class="tynys-json">{}</pre>', json.dumps(value, indent=2, ensure_ascii=False)
    )


class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None
    list_per_page = 50
    show_full_result_count = False
    change_form_template = "admin/tynys/change_form.html"
    workspace_path = ""

    def has_module_permission(self, request):
        return self.admin_site.has_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.admin_site.has_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return self.fields

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        context = {**(extra_context or {}), "operation_url": workspace_url(self.workspace_path)}
        return super().changeform_view(request, object_id, form_url, context)


class ResortRelation:
    @admin.display(description="Санаторий", ordering="resort__name")
    def resort_link(self, obj):
        return record_link(obj.resort, obj.resort.name) if obj.resort_id else "—"


@admin.register(User, site=platform_admin_site)
class StaffAdmin(ResortRelation, ReadOnlyAdmin):
    list_display = (
        "email",
        "name",
        "role",
        "resort_link",
        "is_active",
        "is_superuser",
        "last_login",
    )
    list_filter = ("role", "is_active", "is_superuser", "resort")
    search_fields = ("email", "name", "resort__name")
    list_select_related = ("resort",)
    fields = (
        "id",
        "name",
        "email",
        "role",
        "resort_link",
        "is_active",
        "is_staff",
        "is_superuser",
        "date_joined",
        "last_login",
        "version",
    )
    ordering = ("email",)
    workspace_path = "accounts"


@admin.register(Resort, site=platform_admin_site)
class ResortAdmin(ReadOnlyAdmin):
    list_display = (
        "name",
        "city",
        "status",
        "category",
        "resort_class",
        "check_in_time",
        "time_zone",
        "commission_percent",
    )
    list_filter = ("status", "category", "resort_class", "city")
    search_fields = ("name", "city", "address")
    fields = (
        "id",
        "name",
        "city",
        "address",
        "subtitle",
        "description",
        "feature",
        "lat",
        "lng",
        "status",
        "category",
        "resort_class",
        "check_in_time",
        "time_zone",
        "rating",
        "amenities",
        "media",
        "version",
    )
    ordering = ("name",)
    workspace_path = "resorts"


@admin.register(Room, site=platform_admin_site)
class RoomAdmin(ResortRelation, ReadOnlyAdmin):
    list_display = ("number", "title", "resort_link", "category", "capacity", "price", "status")
    list_filter = ("resort", "status", "category", "capacity")
    search_fields = ("number", "title", "resort__name")
    list_select_related = ("resort",)
    fields = (
        "id",
        "resort_link",
        "number",
        "title",
        "description",
        "category",
        "area",
        "capacity",
        "beds",
        "price",
        "seasonal_prices",
        "status",
        "amenities",
        "media",
        "version",
    )
    ordering = ("resort__name", "number")
    workspace_path = "rooms"

    @admin.display(description="Цены по периодам")
    def seasonal_prices(self, obj):
        return (
            "\n".join(
                f"{p.stay.lower} — {p.stay.upper} (не включая): {p.price} ₸ · {p.label}"
                for p in obj.price_periods.all()
            )
            or "—"
        )


@admin.register(Tariff, site=platform_admin_site)
class TariffAdmin(ResortRelation, ReadOnlyAdmin):
    list_display = ("name", "resort_link", "supplement", "price_kind", "discount_percent", "status")
    list_filter = ("resort", "status", "price_kind")
    search_fields = ("name", "resort__name")
    list_select_related = ("resort",)
    fields = (
        "id",
        "resort_link",
        "name",
        "description",
        "supplement",
        "children_under_three_free",
        "features",
        "price_kind",
        "discount_percent",
        "status",
        "version",
    )
    ordering = ("resort__name", "name")
    workspace_path = "tariffs"


@admin.register(GuestProfile, site=platform_admin_site)
class GuestProfileAdmin(ReadOnlyAdmin):
    list_display = ("name", "phone", "created_at", "updated_at")
    search_fields = ("name", "phone", "=id")
    fields = ("id", "name", "phone", "avatar_link", "created_at", "updated_at", "version")
    list_select_related = ("avatar",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    workspace_path = "bookings"

    @admin.display(description="Аватар")
    def avatar_link(self, obj):
        return record_link(obj.avatar, "Информация о файле") if obj.avatar_id else "—"


@admin.register(GuestAccount, site=platform_admin_site)
class GuestAccountAdmin(ReadOnlyAdmin):
    list_display = ("phone", "profile_link", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("phone", "profile__name", "=id")
    list_select_related = ("profile",)
    fields = ("id", "phone", "profile_link", "is_active", "created_at", "version")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    workspace_path = "bookings"

    @admin.display(description="Профиль гостя", ordering="profile__name")
    def profile_link(self, obj):
        return record_link(obj.profile, obj.profile.name)


@admin.register(Booking, site=platform_admin_site)
class BookingAdmin(ResortRelation, ReadOnlyAdmin):
    list_display = (
        "id",
        "guest_label",
        "resort_link",
        "room_link",
        "stay",
        "status",
        "source",
        "checked_in_at",
        "checked_out_at",
        "created_at",
    )
    list_filter = (
        "status",
        "source",
        "resort",
        ("checked_in_at", admin.EmptyFieldListFilter),
        ("checked_out_at", admin.EmptyFieldListFilter),
    )
    search_fields = ("=id", "guest_label", "guest_phone", "room__number", "resort__name")
    list_select_related = ("resort", "room", "tariff", "guest_profile")
    fields = (
        "id",
        "resort_link",
        "room_link",
        "tariff_link",
        "guest_label",
        "guest_phone",
        "profile_link",
        "stay",
        "guests",
        "status",
        "source",
        "checked_in_at",
        "checked_out_at",
        "created_at",
        "price_and_terms",
        "version",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    workspace_path = "bookings"

    @admin.display(description="Номер", ordering="room__number")
    def room_link(self, obj):
        return record_link(obj.room, f"{obj.room.number} · {obj.room.title}")

    @admin.display(description="Тариф")
    def tariff_link(self, obj):
        return record_link(obj.tariff, obj.tariff.name)

    @admin.display(description="Профиль гостя")
    def profile_link(self, obj):
        return (
            record_link(obj.guest_profile, obj.guest_profile.name) if obj.guest_profile_id else "—"
        )

    @admin.display(description="Зафиксированные цены и условия")
    def price_and_terms(self, obj):
        return structured_data(obj.snapshot)


@admin.register(Review, site=platform_admin_site)
class ReviewAdmin(ResortRelation, ReadOnlyAdmin):
    list_display = ("id", "resort_link", "rating", "status", "created_at")
    list_filter = ("status", "rating", "resort")
    search_fields = ("text", "reply", "booking__guest_label", "resort__name", "=id")
    list_select_related = ("resort", "booking")
    fields = (
        "id",
        "resort_link",
        "booking_link",
        "rating",
        "text",
        "photos",
        "status",
        "reply",
        "created_at",
        "version",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    workspace_path = "reviews"

    @admin.display(description="Бронирование")
    def booking_link(self, obj):
        return record_link(obj.booking)


@admin.register(Audit, site=platform_admin_site)
class AuditAdmin(ResortRelation, ReadOnlyAdmin):
    list_display = ("at", "actor", "entity", "action", "label", "resort_link")
    list_filter = ("entity", "action", "resort")
    search_fields = ("actor", "label", "=entity_id", "resort__name")
    list_select_related = ("resort",)
    fields = (
        "id",
        "at",
        "actor",
        "resort_link",
        "entity",
        "entity_id",
        "action",
        "label",
        "before_data",
        "after_data",
    )
    date_hierarchy = "at"
    ordering = ("-at",)
    workspace_path = "history"

    @admin.display(description="До изменения")
    def before_data(self, obj):
        return structured_data(obj.before)

    @admin.display(description="После изменения")
    def after_data(self, obj):
        return structured_data(obj.after)


@admin.register(MediaAsset, site=platform_admin_site)
class MediaAssetAdmin(ResortRelation, ReadOnlyAdmin):
    list_display = ("id", "purpose", "kind", "size", "resort_link", "created_at")
    list_filter = ("purpose", "kind", "resort")
    search_fields = ("=id", "resort__name", "profile__name", "=booking__id")
    list_select_related = ("resort", "booking", "profile")
    fields = (
        "id",
        "purpose",
        "kind",
        "size",
        "content_type",
        "resort_link",
        "booking_link",
        "profile_link",
        "created_at",
        "version",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    @admin.display(description="Бронирование")
    def booking_link(self, obj):
        return record_link(obj.booking) if obj.booking_id else "—"

    @admin.display(description="Профиль гостя")
    def profile_link(self, obj):
        return record_link(obj.profile, obj.profile.name) if obj.profile_id else "—"
