"""Serverless-safe telemetry: structured request logs and shared database gauges.

No process-local request counters are exported: a scrape can hit a different
Vercel instance. Request latency lives in logs; queue gauges come from PostgreSQL.
"""

import json
import logging
import secrets
import time
import uuid

from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger("tynys.requests")


class RequestTelemetryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = uuid.uuid4().hex
        request.request_id = request_id
        started = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        if settings.REQUEST_LOG_ENABLED and request.path not in {
            "/health/live",
            "/health/ready",
            "/internal/metrics",
        }:
            match = getattr(request, "resolver_match", None)
            # Resolver patterns contain placeholders, never the concrete URL,
            # IDs, query strings, request bodies, IPs or credentials.
            route = str(match.route)[:200] if match else "unmatched"
            method = (
                request.method
                if request.method
                in {
                    "GET",
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE",
                    "HEAD",
                    "OPTIONS",
                }
                else "OTHER"
            )
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "route": route,
                        "method": method,
                        "status": response.status_code,
                        "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    },
                    separators=(",", ":"),
                )
            )
        return response


def gauge(name, description, samples):
    lines = [f"# HELP {name} {description}", f"# TYPE {name} gauge"]
    for labels, value in samples:
        suffix = (
            "{"
            + ",".join(f"{key}={json.dumps(str(item))}" for key, item in sorted(labels.items()))
            + "}"
            if labels
            else ""
        )
        lines.append(f"{name}{suffix} {float(value)!r}")
    return "\n".join(lines) + "\n"


def render_metrics(snapshot):
    """Allowlisted families only; labels are normalized by commerce.operations."""
    from commerce.operations import prometheus_samples

    output = gauge(
        "tynys_metrics_snapshot_timestamp_seconds",
        "Time of this database snapshot.",
        [({}, time.time())],
    )
    return output + "".join(
        gauge(name, help_text, samples) for name, help_text, samples in prometheus_samples(snapshot)
    )


@require_GET
@never_cache
def metrics(request):
    key = settings.METRICS_BEARER_TOKEN
    if len(key) < 32:
        return JsonResponse({"message": "Not found"}, status=404)
    supplied = request.headers.get("Authorization", "")
    if len(supplied) > 512 or not secrets.compare_digest(
        supplied.encode("utf-8"), ("Bearer " + key).encode("utf-8")
    ):
        response = JsonResponse({"message": "Unauthorized"}, status=401)
        response["WWW-Authenticate"] = "Bearer"
        return response
    from commerce.operations import operations_snapshot

    started = time.monotonic()
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '2000ms'")
            snapshot = operations_snapshot()
            cursor.execute("""
                SELECT count(*), current_setting('max_connections')::int,
                       count(*) FILTER (WHERE wait_event_type = 'Lock')
                FROM pg_stat_activity
            """)
            connections, maximum, lock_waits = cursor.fetchone()
        body = render_metrics(snapshot)
        body += gauge(
            "tynys_database_connections",
            "PostgreSQL connections including platform services; not Supavisor clients.",
            [({}, connections)],
        )
        body += gauge(
            "tynys_database_max_connections",
            "PostgreSQL max_connections; not the pooler client limit.",
            [({}, maximum)],
        )
        body += gauge(
            "tynys_database_lock_waits",
            "Visible PostgreSQL sessions waiting for locks.",
            [({}, lock_waits)],
        )
    except DatabaseError:
        # Never replace missing database evidence with healthy zero gauges.
        return JsonResponse({"message": "Metrics temporarily unavailable"}, status=503)
    body += gauge(
        "tynys_metrics_collection_duration_seconds",
        "Database metrics collection duration.",
        [({}, time.monotonic() - started)],
    )
    return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")
