from django.contrib import admin

from booking.admin import ReadOnlyAdmin, platform_admin_site, record_link, structured_data

from .models import DemoPayment, DemoRefund


@admin.register(DemoPayment, site=platform_admin_site)
class DemoPaymentAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "booking_link",
        "resort_name",
        "status",
        "amount",
        "refunded_amount",
        "created_at",
    )
    list_filter = ("status", "outcome", "booking__resort")
    search_fields = ("=id", "=booking__id", "booking__guest_label", "booking__resort__name")
    list_select_related = ("booking__resort",)
    fields = (
        "id",
        "booking_link",
        "resort_name",
        "outcome",
        "status",
        "amount",
        "refunded_amount",
        "receipt_data",
        "created_at",
        "version",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    workspace_path = "bookings"

    @admin.display(description="Бронирование")
    def booking_link(self, obj):
        return record_link(obj.booking)

    @admin.display(description="Санаторий", ordering="booking__resort__name")
    def resort_name(self, obj):
        return obj.booking.resort.name

    @admin.display(description="Снимок демо-квитанции (не банковский чек)")
    def receipt_data(self, obj):
        return structured_data(obj.receipt)


@admin.register(DemoRefund, site=platform_admin_site)
class DemoRefundAdmin(ReadOnlyAdmin):
    list_display = ("id", "payment_link", "amount", "percent", "actor_kind", "created_at")
    list_filter = ("actor_kind", "percent", "payment__booking__resort")
    search_fields = ("=id", "=payment__id", "=payment__booking__id")
    list_select_related = ("payment",)
    fields = (
        "id",
        "payment_link",
        "amount",
        "percent",
        "actor_kind",
        "policy_data",
        "created_at",
        "version",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    workspace_path = "bookings"

    @admin.display(description="Демо-платёж")
    def payment_link(self, obj):
        return record_link(obj.payment)

    @admin.display(description="Применённые условия возврата")
    def policy_data(self, obj):
        return structured_data(obj.policy)
