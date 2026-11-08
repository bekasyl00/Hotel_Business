"""Cash events, booking commitments and manual expenses are separate measures."""

from django.db.models import BigIntegerField, Count, Q, Sum, Value
from django.db.models.fields.json import KT
from django.db.models.functions import Cast, Coalesce, Greatest
from django.utils import timezone

from commerce.models import AccountingExpense

from .expenses import expense_data


def financial_report(resorts, bookings, payments, refunds, start, end, mode, *, selected=False):
    expenses = AccountingExpense.objects.filter(
        occurred_on__gte=start, occurred_on__lte=end, payment_mode=mode
    )
    expenses = (
        expenses.filter(resort__in=resorts)
        if selected
        else expenses.filter(Q(resort__in=resorts) | Q(resort__isnull=True))
    )
    # Grouped aggregates avoid one set of queries per property. No payment joins
    # enter the booking sums, so multiple attempts cannot multiply booking totals.
    confirmed = Q(status="confirmed")
    pending = Q(status="pending", hold_expires_at__gt=timezone.now())
    unpaid_ids = (
        bookings.filter(status="confirmed")
        .exclude(bank_payment__status="succeeded")
        .exclude(demo_payments__outcome="success")
        .values("pk")
    )
    online_amount = Coalesce(
        Cast(KT("snapshot__paymentTerms__onlineAmount"), BigIntegerField()),
        Cast(KT("snapshot__total"), BigIntegerField()),
        output_field=BigIntegerField(),
    )
    onsite_amount = Coalesce(
        Cast(KT("snapshot__paymentTerms__onsiteAmount"), BigIntegerField()),
        Value(0),
        output_field=BigIntegerField(),
    )
    onsite_recorded = Coalesce(
        "onsite_settlement__amount", Value(0), output_field=BigIntegerField()
    )
    annotations = dict(
        confirmedAmount=Sum(
            Cast(KT("snapshot__total"), BigIntegerField()), filter=confirmed, default=0
        ),
        awaitingPayment=Sum(online_amount, filter=pending, default=0),
        confirmedUnpaid=Sum(online_amount, filter=Q(pk__in=unpaid_ids), default=0),
        onsiteDue=Sum(
            Greatest(onsite_amount - onsite_recorded, Value(0), output_field=BigIntegerField()),
            filter=confirmed,
            default=0,
        ),
        onsiteRecorded=Sum("onsite_settlement__amount", default=0),
        commissionEstimate=Sum(
            Cast(KT("snapshot__commissionTerms__amount"), BigIntegerField()),
            filter=confirmed,
            default=0,
        ),
        unconfiguredCommissionCount=Count(
            "pk",
            filter=confirmed
            & (
                Q(snapshot__commissionTerms__amount=None)
                | Q(snapshot__commissionTerms__amount__isnull=True)
            ),
        ),
    )
    order_rows = {
        r.pop("resort_id"): r for r in bookings.values("resort_id").annotate(**annotations)
    }

    def grouped(query, key):
        return {r[key]: r["total"] for r in query.values(key).annotate(total=Sum("amount"))}

    income = grouped(
        payments, "booking__resort_id" if mode == "demo" else "payment__booking__resort_id"
    )
    refunds_by = grouped(refunds, "payment__booking__resort_id")
    costs = grouped(expenses.filter(voided_at__isnull=True), "resort_id")
    totals = {k: sum(row.get(k, 0) for row in order_rows.values()) for k in annotations}
    totals.update(
        received=sum(income.values()),
        refunded=sum(refunds_by.values()),
        expenses=sum(costs.values()),
    )
    totals["net"] = totals["received"] - totals["refunded"]
    rows = []
    for resort in resorts.order_by("name", "id")[:500]:
        row = {k: order_rows.get(resort.pk, {}).get(k, 0) for k in annotations}
        row.update(
            resortId=resort.pk,
            name=resort.name,
            received=income.get(resort.pk, 0),
            refunded=refunds_by.get(resort.pk, 0),
            expenses=costs.get(resort.pk, 0),
        )
        row["net"] = row["received"] - row["refunded"]
        rows.append(row)
    return dict(
        totals=totals,
        byResort=rows,
        resortsTruncated=resorts.count() > 500,
        platformExpenses=costs.get(None, 0),
        expenses=[expense_data(e) for e in expenses.order_by("-occurred_on", "-created_at")[:200]],
        expenseCount=expenses.count(),
    )


def report_xlsx(finance, start, end, mode):
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Сводка"
    summary.append(["Период", str(start), str(end), "Источник", mode])
    summary.append(["Учётные данные платформы; не банковская выписка и не чистая прибыль."])
    summary.append(
        [
            "Проживание и отметки оплаты на месте — по заказам, созданным в периоде; "
            "отметки сотрудников не входят в поступления платформы."
        ]
    )
    labels = dict(
        received="Поступления",
        refunded="Возвраты",
        net="Поступления минус возвраты",
        expenses="Учтённые расходы",
        confirmedAmount="Проживание по оформленным заказам, без комиссии",
        awaitingPayment="Ожидается онлайн-оплата",
        confirmedUnpaid="Оформлены без онлайн-оплаты",
        onsiteDue="Осталось оплатить в санатории по оформленным заказам",
        onsiteRecorded="Оплата в санатории, отмеченная сотрудником по выбранным заказам",
        commissionEstimate="Комиссия по условиям заказов до сверки возвратов",
        unconfiguredCommissionCount="Заказы без настройки комиссии",
    )
    for key, label in labels.items():
        summary.append([label, finance["totals"][key]])
    summary.append(["Расходы платформы без привязки к санаторию", finance["platformExpenses"]])
    sheet = workbook.create_sheet("Санатории")
    sheet.append(["ID", "Санаторий", *labels.values()])
    for row in finance["byResort"]:
        sheet.append([row["resortId"], row["name"], *[row[key] for key in labels]])
    ledger = workbook.create_sheet("Расходы")
    ledger.append(
        [
            "ID",
            "Дата",
            "Санаторий ID",
            "Категория",
            "Сумма KZT",
            "Описание",
            "Источник",
            "Отменён",
            "Причина отмены",
        ]
    )
    for row in finance["expenses"]:
        ledger.append(
            [
                row["id"],
                row["date"],
                row["resortId"] or "Платформа",
                row["category"],
                row["amount"],
                row["description"],
                row["paymentMode"],
                row["voidedAt"] or "",
                row["voidReason"],
            ]
        )
    for sheet in workbook:
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"  # Never execute user text as Excel formula.
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(
                56, max(18, max(len(str(cell.value or "")) for cell in col) + 2)
            )
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
