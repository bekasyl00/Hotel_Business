from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers

from booking.errors import Problem
from booking.models import Audit, Resort
from booking.services import version_check
from commerce.models import AccountingExpense

from .services import StrictInput, require_accountant


class ExpenseInput(StrictInput):
    resortId = serializers.PrimaryKeyRelatedField(
        source="resort", queryset=Resort.objects.all(), allow_null=True
    )
    date = serializers.DateField(source="occurred_on")
    amount = serializers.IntegerField(min_value=1, max_value=1000000000000)
    category = serializers.ChoiceField(
        choices=["bank_fee", "operations", "marketing", "payroll", "taxes", "other"]
    )
    description = serializers.CharField(max_length=240)
    paymentMode = serializers.ChoiceField(
        source="payment_mode", choices=["production", "sandbox", "demo"]
    )
    requestId = serializers.UUIDField(source="request_key")

    def validate_date(self, value):
        if value.year < 2000 or value > timezone.localdate():
            raise serializers.ValidationError(
                "Укажите дату совершённого расхода, не позднее сегодня."
            )
        return value


def expense_data(item):
    return dict(
        id=item.pk,
        version=item.version,
        resortId=item.resort_id,
        date=item.occurred_on.isoformat(),
        amount=item.amount,
        category=item.category,
        description=item.description,
        paymentMode=item.payment_mode,
        voidedAt=item.voided_at.isoformat() if item.voided_at else None,
        voidReason=item.void_reason,
        createdAt=item.created_at.isoformat(),
    )


def audit_expense(item, user, action):
    Audit.objects.create(
        actor=user.name or user.username,
        resort_id=item.resort_id,
        entity="accountingExpenses",
        entity_id=item.pk,
        action=action,
        label=item.pk,
        after={"version": item.version, "amount": item.amount, "paymentMode": item.payment_mode},
    )


@transaction.atomic
def create_expense(request):
    require_accountant(request.user)
    serializer = ExpenseInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    item, created = AccountingExpense.objects.get_or_create(
        request_key=data["request_key"], defaults={**data, "created_by": request.user}
    )
    if not created:
        if item.created_by_id != request.user.pk or any(
            getattr(item, key) != value for key, value in data.items()
        ):
            raise Problem("Ключ запроса использован для другого расхода.", 409)
    else:
        audit_expense(item, request.user, "create")
    return expense_data(item)


@transaction.atomic
def void_expense(request, pk):
    require_accountant(request.user)
    if not isinstance(request.data, dict) or set(request.data) != {"version", "reason"}:
        raise Problem("Передайте версию и причину отмены.")
    reason = serializers.CharField(min_length=3, max_length=240).run_validation(
        request.data["reason"]
    )
    item = get_object_or_404(AccountingExpense.objects.select_for_update(), pk=pk)
    version_check(item, request.data)
    if item.voided_at:
        raise Problem("Расход уже отменён.", 409)
    item.voided_at, item.void_reason = timezone.now(), reason
    item.version += 1
    item.save()
    audit_expense(item, request.user, "void")
    return expense_data(item)
