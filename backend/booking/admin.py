from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Audit, Booking, Resort, Room, Tariff, User


@admin.register(User)
class StaffAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Платформа", {"fields": ("name", "role", "resort", "version")}),
    )


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in [Resort, Room, Tariff, Booking, Audit]:
    admin.site.register(model, ReadOnlyAdmin)
