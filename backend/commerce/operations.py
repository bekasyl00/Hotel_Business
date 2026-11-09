"""Low-cardinality operational snapshots from durable PostgreSQL state.

These are gauges, not event counters: completed jobs/payments/refunds are excluded.
No financial amounts, customer data, merchant identifiers or exception text leave
this module. The authenticated metrics endpoint owns its read transaction/timeout.
"""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Case, CharField, Count, F, Max, Min, Q, Value, When
from django.utils import timezone

from booking.models import Booking

from .models import OperationalHeartbeat, PaymentAttempt, PaymentJob, RefundRequest, WebhookDelivery

HEARTBEATS = ("payment_scheduler", "payment_worker")
PROVIDERS = ("halyk_epay", "xpayment")
ENVIRONMENTS = ("sandbox", "production")
JOB_KINDS = ("create", "verify", "deactivate", "refund", "refund_verify")
JOB_STATES = ("pending", "running", "dead")
PAYMENT_STATES = ("creating", "pending", "reconciliation_required")
REFUND_STATES = ("queued", "submitted", "reconciliation_required")


def label(field, allowed):
    """Normalize inside SQL so unrecognized values cannot grow series cardinality."""
    return Case(
        When(**{f"{field}__in": allowed}, then=F(field)),
        default=Value("other"),
        output_field=CharField(),
    )


def age(now, value):
    return max(0.0, (now - value).total_seconds()) if value else 0.0


def scope(prefix=""):
    return {
        "_provider": label(f"{prefix}provider", PROVIDERS),
        "_environment": label(f"{prefix}environment", ENVIRONMENTS),
    }


def unpack(row):
    return {key.removeprefix("_"): value for key, value in row.items()}


def operations_snapshot(*, now=None):
    """Six aggregate queries, independent of the number of customers or resorts.

    Ages are seconds at collection; a missing heartbeat is explicit, not healthy.
    Webhook figures describe only accepted deliveries in the preceding hour and
    must not be interpreted as provider uptime. No rows are changed by collection.
    """
    now = now or timezone.now()
    due = Q(state="pending", available_at__lte=now)
    expired = Q(state="running", lease_until__lt=now)
    jobs = []
    for row in (
        PaymentJob.objects.exclude(state="done")
        .annotate(
            **scope("payment__"), _kind=label("kind", JOB_KINDS), _state=label("state", JOB_STATES)
        )
        .values("_provider", "_environment", "_kind", "_state")
        .annotate(
            count=Count("pk"),
            due=Count("pk", filter=due),
            expired_leases=Count("pk", filter=expired),
            invalid_leases=Count("pk", filter=Q(state="running", lease_until__isnull=True)),
            oldest_due=Min("available_at", filter=due),
            oldest_expired=Min("lease_until", filter=expired),
        )
        .order_by("_provider", "_environment", "_kind", "_state")
    ):
        row["oldest_due_seconds"] = age(now, row.pop("oldest_due"))
        row["oldest_expired_lease_seconds"] = age(now, row.pop("oldest_expired"))
        jobs.append(unpack(row))

    payments = active_rows(PaymentAttempt, PAYMENT_STATES, now)
    refunds = active_rows(RefundRequest, REFUND_STATES, now, prefix="payment__")
    webhooks = []
    for row in (
        WebhookDelivery.objects.filter(received_at__gte=now - timedelta(hours=1))
        .annotate(**scope("payment__"))
        .values("_provider", "_environment")
        .annotate(received_last_hour=Count("pk"), last_received=Max("received_at"))
        .order_by("_provider", "_environment")
    ):
        row["last_received_seconds"] = age(now, row.pop("last_received"))
        webhooks.append(unpack(row))

    overdue = Q(hold_expires_at__lte=now)
    holds = Booking.objects.filter(status="pending").aggregate(
        overdue=Count("pk", filter=overdue),
        oldest=Min("hold_expires_at", filter=overdue),
        legacy_without_deadline=Count("pk", filter=Q(hold_expires_at__isnull=True)),
    )
    holds["oldest_overdue_seconds"] = age(now, holds.pop("oldest"))
    heartbeats = {
        name: {
            "name": name,
            "status": "missing",
            "seen": False,
            "last_started_timestamp": 0.0,
            "last_success_timestamp": 0.0,
            "last_failure_timestamp": 0.0,
            "duration_seconds": 0.0,
            "processed": 0,
        }
        for name in HEARTBEATS
    }
    for heartbeat in OperationalHeartbeat.objects.filter(name__in=HEARTBEATS):
        heartbeats[heartbeat.name] = {
            "name": heartbeat.name,
            "seen": True,
            "status": heartbeat.status,
            "last_started_timestamp": heartbeat.last_started_at.timestamp(),
            "last_success_timestamp": heartbeat.last_success_at.timestamp()
            if heartbeat.last_success_at
            else 0.0,
            "last_failure_timestamp": heartbeat.last_failure_at.timestamp()
            if heartbeat.last_failure_at
            else 0.0,
            "duration_seconds": heartbeat.duration_seconds,
            "processed": heartbeat.processed,
        }
    return {
        "jobs": jobs,
        "payments": payments,
        "refunds": refunds,
        "webhooks": webhooks,
        "holds": holds,
        "heartbeats": list(heartbeats.values()),
    }


def active_rows(model, states, now, *, prefix=""):
    rows = []
    for row in (
        model.objects.filter(status__in=states)
        .annotate(**scope(prefix), _status=label("status", states))
        .values("_provider", "_environment", "_status")
        .annotate(count=Count("pk"), oldest=Min("created_at"))
        .order_by("_provider", "_environment", "_status")
    ):
        row["oldest_seconds"] = age(now, row.pop("oldest"))
        rows.append(unpack(row))
    return rows


@transaction.atomic
def start_heartbeat(name):
    if name not in HEARTBEATS:
        raise ValueError("Unknown operational heartbeat")
    token, now = uuid4(), timezone.now()
    heartbeat, _ = OperationalHeartbeat.objects.get_or_create(
        name=name, defaults={"run_token": token, "status": "running", "last_started_at": now}
    )
    heartbeat = OperationalHeartbeat.objects.select_for_update().get(pk=heartbeat.pk)
    heartbeat.run_token, heartbeat.status, heartbeat.last_started_at = token, "running", now
    heartbeat.duration_seconds, heartbeat.processed = 0, 0
    heartbeat.save(
        update_fields=["run_token", "status", "last_started_at", "duration_seconds", "processed"]
    )
    return token


def finish_heartbeat(name, token, *, succeeded, duration, processed):
    if name not in HEARTBEATS:
        raise ValueError("Unknown operational heartbeat")
    # A slower previous invocation cannot replace the newer invocation's outcome.
    return OperationalHeartbeat.objects.filter(name=name, run_token=token).update(
        status="succeeded" if succeeded else "failed",
        **{"last_success_at" if succeeded else "last_failure_at": timezone.now()},
        duration_seconds=max(0.0, min(float(duration), 86400.0)),
        processed=max(0, min(int(processed), 100)),
    )


def prometheus_samples(snapshot):
    """Only explicitly named, bounded fields become gauge families."""
    provider_scopes = (
        ("halyk_epay", "sandbox"),
        ("xpayment", "sandbox"),
        ("xpayment", "production"),
    )

    def grouped(section, labels, combinations):
        rows = {values: dict(zip(labels, values, strict=True)) for values in combinations}
        for row in snapshot[section]:
            rows[tuple(row[key] for key in labels)] = row
        return list(rows.values())

    jobs = grouped(
        "jobs",
        ("provider", "environment", "kind", "state"),
        (
            (*provider, kind, state)
            for provider in provider_scopes
            for kind in JOB_KINDS
            for state in JOB_STATES
        ),
    )
    definitions = [
        ("payment_jobs", "Unfinished durable payment jobs by state.", "count"),
        ("payment_jobs_due", "Pending jobs whose available_at is due.", "due"),
        (
            "payment_job_oldest_due_seconds",
            "Age of the oldest due pending job in seconds.",
            "oldest_due_seconds",
        ),
        (
            "payment_job_expired_leases",
            "Running jobs with expired leases, eligible for reclaim.",
            "expired_leases",
        ),
        (
            "payment_job_oldest_expired_lease_seconds",
            "Seconds since the oldest running job lease expired.",
            "oldest_expired_lease_seconds",
        ),
        (
            "payment_job_invalid_leases",
            "Running jobs missing a required lease deadline.",
            "invalid_leases",
        ),
    ]
    for name, help_text, field in definitions:
        yield (
            "tynys_" + name,
            help_text,
            [
                (
                    {label: row[label] for label in ("provider", "environment", "kind", "state")},
                    row.get(field, 0),
                )
                for row in jobs
            ],
        )
    for section, states, noun in (
        ("payments", PAYMENT_STATES, "payment"),
        ("refunds", REFUND_STATES, "refund"),
    ):
        rows = grouped(
            section,
            ("provider", "environment", "status"),
            ((*provider, state) for provider in provider_scopes for state in states),
        )
        for suffix, field, description in (
            (f"{noun}s_active", "count", "Unresolved records, excluding terminal history."),
            (
                f"{noun}_oldest_active_seconds",
                "oldest_seconds",
                "Age of the oldest unresolved record in seconds.",
            ),
        ):
            yield (
                "tynys_" + suffix,
                description,
                [
                    (
                        {label: row[label] for label in ("provider", "environment", "status")},
                        row.get(field, 0),
                    )
                    for row in rows
                ],
            )
    webhooks = grouped("webhooks", ("provider", "environment"), provider_scopes)
    yield (
        "tynys_webhook_deliveries_last_hour",
        "Accepted deduplicated deliveries in the preceding hour, not provider uptime.",
        [
            (
                {label: row[label] for label in ("provider", "environment")},
                row.get("received_last_hour", 0),
            )
            for row in webhooks
        ],
    )
    for name, field, description in (
        (
            "booking_holds_overdue",
            "overdue",
            "Pending bookings whose payment deadline has elapsed.",
        ),
        (
            "booking_hold_oldest_overdue_seconds",
            "oldest_overdue_seconds",
            "Seconds since the oldest pending payment deadline elapsed.",
        ),
        (
            "booking_holds_legacy",
            "legacy_without_deadline",
            "Historical pending bookings without a payment deadline; not automatically expired.",
        ),
    ):
        yield "tynys_" + name, description, [({}, snapshot["holds"][field])]
    for name, field, description in (
        ("heartbeat_present", "seen", "Whether this worker has ever reported a durable heartbeat."),
        (
            "last_started_timestamp_seconds",
            "last_started_timestamp",
            "Unix timestamp of latest invocation start, zero if absent.",
        ),
        (
            "last_success_timestamp_seconds",
            "last_success_timestamp",
            "Unix timestamp of latest completed successful invocation, zero if absent.",
        ),
        (
            "last_failure_timestamp_seconds",
            "last_failure_timestamp",
            "Unix timestamp of latest failed invocation, zero if absent.",
        ),
        (
            "run_duration_seconds",
            "duration_seconds",
            "Duration of latest finished invocation, not an event counter.",
        ),
        (
            "run_processed",
            "processed",
            "Jobs processed in latest invocation, not an event counter.",
        ),
    ):
        yield (
            "tynys_worker_" + name,
            description,
            [
                (
                    {"worker": row["name"]},
                    int(row[field]) if isinstance(row[field], bool) else row[field],
                )
                for row in snapshot["heartbeats"]
            ],
        )
    yield (
        "tynys_worker_state",
        "Latest invocation state; exactly one state per worker is one.",
        [
            ({"worker": row["name"], "state": state}, int(row["status"] == state))
            for row in snapshot["heartbeats"]
            for state in ("missing", "running", "succeeded", "failed")
        ],
    )
