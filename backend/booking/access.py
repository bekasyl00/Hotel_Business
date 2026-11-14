"""Staff scope, guest ownership and mutation preconditions shared by domains."""

import secrets

from django.db import connection

from .errors import Problem
from .models import Resort


def admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == "admin")


def lock_account_assignments():
    # Serialize ownership/role changes across platform admins. No personal data in lock key.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(74696879)")


def scoped_resorts(user):
    return (
        Resort.objects.all()
        if admin(user) or user.role == "accountant"
        else Resort.objects.filter(account=user)
    )


def require_staff(user, resort_id=None, *, roles=("admin", "manager")):
    if not user.is_authenticated:
        raise Problem("Войдите в кабинет сотрудника.", 401)
    if not user.is_active or (not user.is_superuser and user.role not in roles):
        raise Problem("Эта операция недоступна вашей роли.", 403)
    if resort_id and connection.in_atomic_block:
        list(Resort.objects.select_for_update().filter(pk=resort_id).values_list("pk", flat=True))
    if (
        not admin(user)
        and user.role != "accountant"
        and resort_id
        and not Resort.objects.filter(pk=resort_id, account=user).exists()
    ):
        raise Problem("У вас нет доступа к этому санаторию.", 403)


def require_admin(user):
    require_staff(user)
    if not admin(user):
        raise Problem("Доступно только администратору.", 403)


def guest_owner(request):
    from .guest_auth import current_account

    account = current_account(request)
    if account:
        return account.profile.owner
    if "guest_owner" not in request.session:
        request.session["guest_owner"] = secrets.token_hex(32)
    return request.session["guest_owner"]


def version_check(item, data):
    if type(data.get("version")) is not int or data["version"] != item.version:
        raise Problem("Запись уже изменена. Обновите данные и повторите.", 409)
