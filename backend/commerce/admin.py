from django.contrib import admin

from booking.admin import ReadOnlyAdmin, platform_admin_site, record_link, structured_data

from .models import (
    AccountingCompany,
    AccountingDocument,
    DemoPayment,
    DemoRefund,
    PaymentAttempt,
    PaymentEvent,
    PaymentJob,
    RefundRequest,
)


@admin.register(AccountingDocument, site=platform_admin_site)
class AccountingDocumentAdmin(ReadOnlyAdmin):
    fields = (
        "id",
        "booking",
        "kind",
        "state",
        "number",
        "version",
        "created_at",
        "released_at",
        "voided_at",
    )
    list_display = ("number", "booking", "kind", "state", "created_at")
    list_filter = ("kind", "state", "booking__resort")
    search_fields = ("=id", "number", "=booking__id")
    workspace_path = "accounting"


@admin.register(AccountingCompany, site=platform_admin_site)
class AccountingCompanyAdmin(ReadOnlyAdmin):
    fields = ("resort", "version", "updated_at")
    list_display = ("resort", "version", "updated_at")
    search_fields = ("resort__name",)
    workspace_path = "accounting"


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


@admin.register(PaymentAttempt, site=platform_admin_site)
class BankPaymentAdmin(ReadOnlyAdmin):
    fields = (
        "id",
        "booking",
        "provider",
        "environment",
        "status",
        "amount",
        "currency",
        "invoice_id",
        "invoice_link_id",
        "bank_status",
        "expires_at",
        "applied_at",
        "last_verified_at",
        "reconciliation_reason",
        "created_at",
    )
    list_display = ("id", "booking", "environment", "status", "amount", "reconciliation_reason")
    list_filter = ("status", "environment", "booking__resort")
    search_fields = ("=id", "=invoice_id", "=booking__id")
    workspace_path = "bookings"


@admin.register(PaymentEvent, site=platform_admin_site)
class BankEventAdmin(ReadOnlyAdmin):
    fields = (
        "id",
        "payment",
        "environment",
        "transaction_id",
        "kind",
        "amount",
        "currency",
        "applied",
        "bank_status",
        "created_at",
    )
    list_display = ("id", "kind", "amount", "applied", "created_at")
    workspace_path = "bookings"


@admin.register(RefundRequest, site=platform_admin_site)
class BankRefundAdmin(ReadOnlyAdmin):
    fields = (
        "id",
        "payment",
        "amount",
        "percent",
        "status",
        "submitted_at",
        "confirmed_at",
        "reconciliation_reason",
    )
    list_display = ("id", "payment", "amount", "status")
    workspace_path = "bookings"


@admin.register(PaymentJob, site=platform_admin_site)
class BankJobAdmin(ReadOnlyAdmin):
    fields = (
        "id",
        "payment",
        "kind",
        "state",
        "attempts",
        "available_at",
        "lease_until",
        "last_error",
    )
    list_display = ("id", "kind", "state", "attempts", "last_error")
    workspace_path = "bookings"
